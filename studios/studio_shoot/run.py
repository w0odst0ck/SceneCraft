"""Studio Shoot — 分镜站（归入 Agent：director + cinematographer + actor）

输入产物：01_script/script.json（Script）+ 02_art/visual_bible.json（VisualBible）
Agent 调用链（S2 分批：按 script.scenes 逐场生成 + 合并，让链路对模型上下文规模不敏感）：
  1. director        逐场调用（大场再按镜头组细分）→ 输出本场镜头；合并时代码补全局连续 shot_id
  2. cinematographer（逐场分批）补摄影参数：机位/焦段/光圈/运镜/布光/景深
  3. actor（逐场分批）     补表演细节：表情/肢体/情绪潜台词/视线
  分批结果按 shot_id 合并进 Shot（补进 lighting / action / emotion 等现有字段，
  不扩展契约，保证下游只读契约字段即可）。
输出产物：<artifacts>/<project_id>/03_shoot/shot_list.json（契约 schemas/shot_list.py::ShotList，
结构与字段与分批前完全一致）
manifest key：shoot ↔ 磁盘目录 03_shoot（映射见 SKILL.md）
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.script import Script
from schemas.shot_list import Shot, ShotList
from schemas.visual_bible import VisualBible
from studios import common
from studios.agent_utils import (
    JSONParseError,
    NoKeyError,
    AgentCaller,
    append_output_contract,
    as_dict,
    call_agent_json_batched,
    count_batch_key,
    group_shots_by_scene,
)

STUDIO_KEY = "shoot"
OUTPUT_FILE = "shot_list.json"
INPUTS: list[tuple[str, str, type]] = [
    ("script", "script.json", Script),
    ("art", "visual_bible.json", VisualBible),
]
SOUL_DIR = Path(__file__).parent / "agents"  # director.md / cinematographer.md / actor.md

# ── S2 分批参数（按场景分批，根治 ctx 截断）────────────────
# 批次边界 = 剧本场景（每场一次调用）；单场预估过大时本场再按镜头组细分。
DIRECTOR_SPLIT_SEC = 20.0     # 单场时长超此阈值 → 本场按镜头组再细分（简单阈值常量）
SHOTS_PER_SUB_BATCH = 4       # 细分时每组预估镜头数（3-4 镜一组）
ASSUMED_SEC_PER_SHOT = 6.0    # 由场时长预估镜头数（仅用于细分估算）

# director 单次输出契约示例（ShotList 结构；示例仅 1 镜，避免契约本身撑爆 ctx）
_SHOT_LIST_CONTRACT = json.dumps(ShotList.demo().model_dump(mode="json"), ensure_ascii=False)

# cinematographer / actor 无独立契约类：输出为 {shot_id: {...}} 映射，
# 字段与 _merge_refinements 消费的完全一致（参考 demo 实现，Phase B.1 注入用）
_CAMERA_CONTRACT = json.dumps({
    "SHOT_1": {
        "camera_angle": "平视中景",
        "focal_length": "35mm",
        "aperture": "f/1.8",
        "camera_movement": "固定",
        "lighting_setup": "冷色顶灯 + 霓虹",
        "depth_of_field": "中景深",
    },
}, ensure_ascii=False)
_PERFORMANCE_CONTRACT = json.dumps({
    "SHOT_1": {
        "expression": "警觉、微微皱眉",
        "body_language": "静止倾听",
        "emotional_subtext": "平静",
        "gaze_direction": "直视对方",
    },
}, ensure_ascii=False)


def _join(*parts: str | None) -> str:
    """把非空片段用「；」拼接，用于把摄影/表演细节织入现有字段（信息不丢）。"""
    return "；".join(p for p in parts if p and str(p).strip())


def _merge_refinements(shot_list: ShotList, cam: dict, perf: dict) -> ShotList:
    """把 cinematographer（cam）与 actor（perf）的细化按 shot_id 合并进 Shot。"""
    cam = cam or {}
    perf = perf or {}
    merged: list[Shot] = []
    for shot in shot_list.shots:
        c = cam.get(shot.shot_id) or {}
        p = perf.get(shot.shot_id) or {}
        merged.append(shot.model_copy(update={
            "camera_angle": c.get("camera_angle") or shot.camera_angle,
            "focal_length": c.get("focal_length") or shot.focal_length,
            "camera_movement": c.get("camera_movement") or shot.camera_movement,
            "lighting": _join(
                shot.lighting, c.get("lighting_setup"),
                (f"光圈 {c.get('aperture')}" if c.get("aperture") else None),
                (f"景深 {c.get('depth_of_field')}" if c.get("depth_of_field") else None),
            ),
            "action": _join(shot.action, p.get("body_language"), p.get("expression")),
            "emotion": _join(shot.emotion, p.get("emotional_subtext")),
        }))
    # 合并后整体重新校验（pydantic v2 model_copy 不校验，LLM 合并值可能破坏契约）
    result = shot_list.model_copy(update={"shots": merged})
    return ShotList.model_validate(result.model_dump(mode="json"))


def _director_batches(script: Script) -> list[dict[str, Any]]:
    """按 script.scenes 构造 director 批次（每场 1 批）；单场预估过大时再按镜头组细分。

    返回每批的元信息：本场 scene（dict）+ scene_id + 组序号 + 组内预估镜数
    （组信息仅用于提示模型分镜规模，合并时只用 scene_id 归属 + 顺序）。
    """
    batches: list[dict[str, Any]] = []
    for scene in script.scenes:
        scene_dict = scene.model_dump(mode="json")
        duration = float(scene.duration_sec or 0.0)
        if duration <= DIRECTOR_SPLIT_SEC:
            batches.append({
                "scene": scene_dict, "scene_id": scene.scene_id,
                "group_index": 1, "group_total": 1, "est_shots": None,
            })
            continue
        # 兜底细分：预估镜数 = 场时长 / 每镜秒数，按每 SHOTS_PER_SUB_BATCH 镜一组切分
        est_total = max(1, math.ceil(duration / ASSUMED_SEC_PER_SHOT))
        group_total = max(1, math.ceil(est_total / SHOTS_PER_SUB_BATCH))
        per_group = math.ceil(est_total / group_total)
        for g in range(group_total):
            batches.append({
                "scene": scene_dict, "scene_id": scene.scene_id,
                "group_index": g + 1, "group_total": group_total,
                "est_shots": max(1, min(per_group, est_total - g * per_group)),
            })
    return batches


def _director_prompt(vb: VisualBible, batch: dict[str, Any]) -> str:
    """构造单个 director 批次输入：visual_bible 全量（跨场一致性）+ 本场 scene + 契约。"""
    payload: dict[str, Any] = {
        "visual_bible": vb.model_dump(mode="json"),
        "scene": batch["scene"],
    }
    if batch["group_total"] > 1:  # 细分批次：告知本组序号与预估镜数
        payload["shot_group"] = {
            "index": batch["group_index"],
            "total": batch["group_total"],
            "estimated_shots": batch["est_shots"],
        }
    return append_output_contract(json.dumps(payload, ensure_ascii=False), _SHOT_LIST_CONTRACT)


def _batch_label(meta: dict[str, Any]) -> str:
    """批次标识（报错用）：细分组带组序号，便于对照批次进度日志定位。"""
    total = int(meta.get("group_total") or 1)
    if total <= 1:
        return str(meta["scene_id"])
    return f"{meta['scene_id']} 第 {meta.get('group_index')}/{total} 组"


def _merge_director(metas: list[dict[str, Any]], results: list[Any]) -> dict[str, Any]:
    """合并各场 director 输出：代码补全局连续 shot_id + scene_id 归属，再汇总 target_shots。

    shot_id / scene_id 一律由代码重写（不信模型自填），保证全局连续、场次归属正确；
    **按批次**（而非按场）校验空产出：大场细分成多组时，某组 0 镜不得因兄弟组有镜
    而被场级汇总掩盖 → 任一批次 0 镜即明确失败（不静默丢该组镜头）。
    """
    shots: list[dict[str, Any]] = []
    empty_batches: list[str] = []
    n = 0
    for meta, res in zip(metas, results):
        scene_id = meta["scene_id"]
        # 类型防护：raw safe_parse_json 可能返回顶层 list（非 dict）→ 取空 dict（记为空批次）
        batch_shots = [item for item in as_dict(res).get("shots") or [] if isinstance(item, dict)]
        if not batch_shots:
            empty_batches.append(_batch_label(meta))
        for item in batch_shots:
            n += 1
            shot = dict(item)
            shot["shot_id"] = f"SHOT_{n}"        # 全局连续编号
            shot["scene_id"] = scene_id          # 本场归属
            shots.append(shot)
    if empty_batches:
        raise RuntimeError(
            f"director 分批生成存在空批次（未产出任何镜头）：{'、'.join(empty_batches)}"
        )
    return {"target_shots": len(shots), "shots": shots}


def _merge_maps(results: list[Any]) -> dict[str, Any]:
    """合并各批 {shot_id: {...}} 映射为一整份（后出现的同 shot_id 覆盖前值）。

    批次结果非 dict（raw safe_parse_json 可能返回顶层 list）说明该批输出不合法 →
    明确报错，不静默丢弃该批（否则整场细化被丢且下游无感）；批内非 dict 的值不采纳
    （下游对未覆盖镜打印告警）。
    """
    merged: dict[str, Any] = {}
    for idx, res in enumerate(results, start=1):
        if not isinstance(res, dict):
            raise RuntimeError(
                f"第 {idx} 批细化输出不是 {{shot_id: 字段}} 对象（实际 {type(res).__name__}）"
            )
        for shot_id, fields in res.items():
            if isinstance(fields, dict):
                merged[str(shot_id)] = fields
    return merged


def _refine_prompt(shots: list[Shot], contract: str) -> str:
    """构造单个 cinematographer / actor 批次输入：本场镜头子集 + 单镜字段契约。"""
    return append_output_contract(
        json.dumps({
            "shot_list": {
                "target_shots": len(shots),
                "shots": [s.model_dump(mode="json") for s in shots],
            },
        }, ensure_ascii=False),
        contract,
    )


def build_artifact(args: Any, inputs: dict[str, Any], caller: AgentCaller) -> ShotList:
    """director 逐场分批拆解分镜 → cinematographer + actor 逐场分批细化 → 合并。"""
    script: Script = inputs["script"]  # type: ignore[assignment]
    vb: VisualBible = inputs["art"]  # type: ignore[assignment]

    # 1) director：按 script.scenes 逐场分批（大场再细分），合并时代码补全局 shot_id
    batches = _director_batches(script)
    print(f"   🎬 director 分批：{len(batches)} 批（剧本 {len(script.scenes)} 场）")
    shot_list = call_agent_json_batched(
        caller, "director", "director",
        [_director_prompt(vb, b) for b in batches],
        merge_fn=lambda results: _merge_director(batches, results),
        model_class=ShotList,
        count_fn=lambda res: count_batch_key(res, "shots"),  # dict-safe（可能顶层 list）
    )
    print(f"   ✅ director：{len(shot_list.shots)} 个镜头")

    # 2) cinematographer + actor：按同一批次边界（逐场）分批，输出 {shot_id: {...}} 合并
    scene_groups = group_shots_by_scene(shot_list)
    print(f"   🎥 cinematographer + actor 分批：{len(scene_groups)} 批（逐场）")
    cam = call_agent_json_batched(
        caller, "cinematographer", "cinematographer",
        [_refine_prompt(shots, _CAMERA_CONTRACT) for _, shots in scene_groups],
        merge_fn=_merge_maps,
    )
    perf = call_agent_json_batched(
        caller, "actor", "actor",
        [_refine_prompt(shots, _PERFORMANCE_CONTRACT) for _, shots in scene_groups],
        merge_fn=_merge_maps,
    )
    print(f"   ✅ cinematographer + actor：{len(cam or {})}/{len(perf or {})} 镜细化完成")

    # 细化覆盖提示：某镜缺细化时保留 director 原值（细化字段契约均有缺省，故仅告警
    # 不报错；但不静默——缺哪些镜明确打印，便于对照批次日志发现漏镜）
    expected_ids = {s.shot_id for s in shot_list.shots}
    for label, refined in (("cinematographer", cam or {}), ("actor", perf or {})):
        missing = sorted(expected_ids - set(refined))
        if missing:
            print(f"   ⚠ {label} 未覆盖 {len(missing)} 镜细化（保留 director 原值）："
                  f"{'、'.join(missing)}")

    # 3) 合并进 Shot（契约字段不变）
    return _merge_refinements(shot_list, cam, perf)


def main(argv: list[str] | None = None) -> int:
    args = common.build_parser("Studio Shoot：分镜站（director + cinematographer + actor）").parse_args(argv)
    project = common.project_dir(args.artifacts_dir, args.project)

    # 加载输入产物（缺 script / visual_bible 时友好报错，提示先跑上游）
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
