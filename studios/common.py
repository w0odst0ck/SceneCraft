"""studios/common.py — 各工作室 run.py 共享工具

提供：stage 目录映射、输入产物加载（含友好报错）、manifest 读写、
产物落盘（计算 output_hash + 更新台账）、时间戳。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from schemas.artifact import content_hash
from schemas.manifest import Manifest, StudioStatus

# 工作室短名（manifest 的 studios key）→ 磁盘 stage 目录名（唯一映射，与各 SKILL.md 同步维护）
STAGE_DIRS: dict[str, str] = {
    "script": "01_script",
    "art": "02_art",
    "shoot": "03_shoot",
    "prompt": "04_prompt",
    "edit": "05_edit",
    "render": "06_render",
    "qc": "07_qc",
}

# 各 stage 的默认产物文件名（qc 站按短名定位目标产物用）
DEFAULT_FILES: dict[str, str] = {
    "script": "script.json",
    "art": "visual_bible.json",
    "shoot": "shot_list.json",
    "prompt": "prompt_list.json",
    "edit": "editing_blueprint.json",
    "render": "render_plan.json",
    "qc": "qc_report.json",
}

T = TypeVar("T", bound=BaseModel)


class InputError(Exception):
    """输入产物缺失或校验失败（缺上游产物时抛出，提示先跑上游工作室）。"""


class HumanEditError(Exception):
    """目标产物已被人工修改（edited_by=human），拒绝 AI 覆盖（血缘保护最简版）。"""


def now_iso() -> str:
    """当前 UTC 时间（ISO 8601，秒精度），用于 manifest 的 started_at / finished_at。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# 说明：content_hash 直接复用 schemas.artifact.content_hash（同一口径），
# 供 qc 站对无 schema 的输入/输出计算 hash。


def project_dir(artifacts_dir: str | Path, project_id: str) -> Path:
    """<artifacts_dir>/<project_id> 项目目录。"""
    return Path(artifacts_dir) / project_id


def build_parser(desc: str, concept: bool = False) -> argparse.ArgumentParser:
    """构造统一 CLI：--project（必填）+ --artifacts-dir（默认 artifacts/）。

    concept=True 时额外提供 --concept（Studio Story 站用，接收用户概念字符串）。
    """
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--project", required=True, help="项目 ID，如 demo1（对应 artifacts/<project_id>/）")
    parser.add_argument("--artifacts-dir", default="artifacts/", help="产物仓库根目录（默认 artifacts/）")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="demo 模式：不调用 DeepSeek，使用内置演示输出（无需 API key）",
    )
    if concept:
        parser.add_argument(
            "--concept",
            default="TODO_PHASE_B: 用户概念待 Phase B 接入",
            help="用户创意概念（短句）",
        )
    return parser


def load_input(path: Path, model: type[T]) -> T:
    """读取单个输入产物 JSON 并做 pydantic 校验。

    产物缺失 / 非法 JSON / 校验失败时抛 InputError，消息提示先运行上游工作室。
    """
    if not path.exists():
        raise InputError(
            f"缺少输入产物：{path}\n提示：请先运行上游工作室生成该产物，再重跑本工作室。"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return model.model_validate(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"输入产物不是合法 JSON：{path}\n解析错误：{exc}") from exc
    except ValidationError as exc:
        raise InputError(f"输入产物与契约不匹配：{path}\n校验错误：{exc}") from exc


def load_inputs(project: Path, inputs: list[tuple[str, str, type[BaseModel]]]) -> dict[str, BaseModel]:
    """按 [(短名, 文件名, 契约类)] 批量加载输入产物，返回 {短名: 实例}。

    任一输入缺失或校验失败都会抛 InputError（由 run.py 统一友好报错）。
    """
    loaded: dict[str, BaseModel] = {}
    for key, filename, model in inputs:
        loaded[key] = load_input(project / STAGE_DIRS[key] / filename, model)
    return loaded


def load_raw(path: Path) -> dict:
    """读取任意站产物 JSON（qc 站用，不绑定具体契约，仅要求是 JSON 对象）。"""
    if not path.exists():
        raise InputError(
            f"缺少输入产物：{path}\n提示：请先运行对应工作室生成该产物，再跑质检。"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"输入产物不是合法 JSON：{path}\n解析错误：{exc}") from exc
    if not isinstance(data, dict):
        raise InputError(f"输入产物结构异常（应为 JSON 对象）：{path}")
    return data


def upstream_hashes(inputs: dict[str, BaseModel]) -> dict[str, str]:
    """从输入产物实例收集血缘 hash：优先取产物自带 output_hash，缺失则现场计算。"""
    hashes: dict[str, str] = {}
    for key, inst in inputs.items():
        own = getattr(inst, "output_hash", None)
        hashes[key] = own if isinstance(own, str) else inst.compute_hash()  # type: ignore[attr-defined]
    return hashes


def load_manifest(project: Path) -> Manifest:
    """读取项目 manifest；不存在则新建（created_at 记当前时间）。"""
    mf_path = project / "manifest.json"
    if mf_path.exists():
        return Manifest.model_validate(json.loads(mf_path.read_text(encoding="utf-8")))
    return Manifest(project_id=project.name, created_at=now_iso())


def save_manifest(project: Path, manifest: Manifest) -> Path:
    """把 manifest 写回 <project>/manifest.json。"""
    mf_path = project / "manifest.json"
    mf_path.parent.mkdir(parents=True, exist_ok=True)
    mf_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return mf_path


def mark_start(manifest: Manifest, key: str, upstream: dict[str, str]) -> None:
    """run 开始：置 running + 记录上游血缘 + started_at。"""
    st = manifest.studios.get(key) or StudioStatus()
    st.status = "running"
    st.started_at = now_iso()
    st.upstream_hash = upstream
    manifest.studios[key] = st


def mark_done(manifest: Manifest, key: str, artifact: BaseModel) -> None:
    """run 完成：置 done + 回填 version / output_hash / finished_at。"""
    st = manifest.studios[key]
    st.status = "done"
    st.version = artifact.version
    st.output_hash = artifact.output_hash
    st.finished_at = now_iso()
    manifest.current_focus = key  # 完成即标记为焦点，便于断点续跑定位下一步


def write_artifact(project: Path, key: str, filename: str, artifact: T) -> Path:
    """落盘产物：计算并回填 output_hash → 写 <project>/<stage>/<filename>.json。

    人工产物保护：目标文件已存在且 edited_by == "human" 时抛 HumanEditError，
    拒绝覆盖人工修改（重跑前需删除文件或将其改回 edited_by=ai）。
    """
    artifact.output_hash = artifact.compute_hash()
    stage_dir = project / STAGE_DIRS[key]
    stage_dir.mkdir(parents=True, exist_ok=True)
    out_path = stage_dir / filename
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = None
        if isinstance(existing, dict) and existing.get("edited_by") == "human":
            raise HumanEditError(
                f"该产物为人工修改（edited_by=human），拒绝覆盖：{out_path}\n"
                "如需重跑请先删除该文件，或将其 edited_by 改回 ai。"
            )
    out_path.write_text(
        json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_path
