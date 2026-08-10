"""Studio Edit — 剪辑站（归入 Agent：editor）

输入产物：03_shoot/shot_list.json（ShotList）+ 01_script/script.json（Script）
Agent 调用链：editor 按 shot_list 排时间线（入出帧 + 转场，对齐 script 情绪曲线），
  并标注音频落点（AudioBeat）
输出产物：<artifacts>/<project_id>/05_edit/editing_blueprint.json
  （契约 schemas/editing_blueprint.py::EditingBlueprint）
manifest key：edit ↔ 磁盘目录 05_edit（映射见 SKILL.md）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.editing_blueprint import EditingBlueprint
from schemas.script import Script
from schemas.shot_list import ShotList
from studios import common
from studios.agent_utils import JSONParseError, NoKeyError, AgentCaller, append_output_contract, call_agent_json

STUDIO_KEY = "edit"
OUTPUT_FILE = "editing_blueprint.json"
INPUTS: list[tuple[str, str, type]] = [
    ("shoot", "shot_list.json", ShotList),
    ("script", "script.json", Script),
]
SOUL_DIR = Path(__file__).parent / "agents"  # editor.md


def build_artifact(args: Any, inputs: dict[str, Any], caller: AgentCaller) -> EditingBlueprint:
    """editor：shot_list + script → 剪辑时间线蓝图（含音频落点）。"""
    shot_list: ShotList = inputs["shoot"]  # type: ignore[assignment]
    script: Script = inputs["script"]  # type: ignore[assignment]
    # 注入 EditingBlueprint 契约示例（timeline / audio_beats），约束真实输出格式
    user_prompt = append_output_contract(
        json.dumps({
            "shot_list": shot_list.model_dump(mode="json"),
            "script": script.model_dump(mode="json"),
        }, ensure_ascii=False),
        json.dumps(EditingBlueprint.demo().model_dump(mode="json"), ensure_ascii=False),
    )
    return call_agent_json(caller, "editor", "editor", user_prompt, model_class=EditingBlueprint)


def main(argv: list[str] | None = None) -> int:
    args = common.build_parser("Studio Edit：剪辑站（editor）").parse_args(argv)
    project = common.project_dir(args.artifacts_dir, args.project)

    # 加载输入产物（缺 shot_list / script 时友好报错，提示先跑上游）
    inputs = common.load_inputs(project, INPUTS)

    caller = AgentCaller(demo_mode=args.demo, soul_dir=SOUL_DIR)
    artifact = build_artifact(args, inputs, caller)

    manifest = common.load_manifest(project)
    common.mark_start(manifest, STUDIO_KEY, common.upstream_hashes(inputs))
    out_path = common.write_artifact(project, STUDIO_KEY, OUTPUT_FILE, artifact)
    common.mark_done(manifest, STUDIO_KEY, artifact)
    manifest.studios[STUDIO_KEY].cost_usd = caller.cost_usd()
    common.save_manifest(project, manifest)

    print(f"输出产物：{out_path}")
    print(f"项目台账：{project / 'manifest.json'}")
    print(f"本次 Agent 成本：${caller.cost_usd():.6f}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (common.InputError, common.HumanEditError, NoKeyError,
            JSONParseError, ValidationError, RuntimeError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)
