"""Studio Edit — 剪辑站（归入 Agent：editor）

输入产物：03_shoot/shot_list.json（ShotList）+ 01_script/script.json（Script）
Agent 调用链（S2 分批：与 shoot/prompt 同源的场景边界逐场调用 + 合并）：
  editor 按 shot_list **逐场分批**排时间线（入出帧 + 转场，对齐 script 情绪曲线），
  并标注音频落点（AudioBeat）。每批只消费本场镜头子集 + 本场 scene；
  合并时**由代码按全局镜头顺序补帧号**（参考 shoot 补 shot_id 的模式：不信模型
  自填的跨批连续性）——start_frame / end_frame 逐镜累加、total_frames = 实际总和，
  保证 timeline 条数与 shot_list 镜数一致且帧号连续。
输出产物：<artifacts>/<project_id>/05_edit/editing_blueprint.json
  （契约 schemas/editing_blueprint.py::EditingBlueprint，结构与字段不变）
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

STUDIO_KEY = "edit"
OUTPUT_FILE = "editing_blueprint.json"
INPUTS: list[tuple[str, str, type]] = [
    ("shoot", "shot_list.json", ShotList),
    ("script", "script.json", Script),
]
SOUL_DIR = Path(__file__).parent / "agents"  # editor.md

# ── S2 分批参数（与 shoot/prompt 同源场景边界，根治 ctx 截断与静默缺镜）──
# 批次边界 = 剧本场景（逐场）；单场镜数超过上限时本场再按镜组细分（复用 agent_utils
# 的 group_shots_by_scene），控制单次输入/输出规模（ctx 受限模型）。
EDIT_SHOTS_PER_BATCH = 6
# 模型未给合法 target_fps 时回退契约缺省（EditingBlueprint.demo().target_fps）
DEFAULT_FPS = EditingBlueprint.demo().target_fps


def _editor_batches(script: Script, shot_list: ShotList) -> list[dict[str, Any]]:
    """构造 editor 批次：批次边界与 shoot/prompt 同源（逐场），大场按镜组细分。

    返回每批：本场 scene（供模型对齐该场情绪曲线；script 中找不到同 scene_id 时为
    None）+ 本场镜头子集（全局顺序）。同一 scene_id 可能因细分出现多个连续批次。
    """
    scene_by_id = {s.scene_id: s.model_dump(mode="json") for s in script.scenes}
    return [
        {"scene_id": scene_id, "scene": scene_by_id.get(scene_id), "shots": shots}
        for scene_id, shots in group_shots_by_scene(
            shot_list, max_shots_per_batch=EDIT_SHOTS_PER_BATCH
        )
    ]


def _editor_prompt(batch: dict[str, Any], contract: str) -> str:
    """构造单个 editor 批次输入：本场镜头子集 + 本场 scene + EditingBlueprint 契约。

    帧号（start_frame / end_frame / total_frames）由代码在合并阶段统一补全，
    模型只需给出每镜的转场与音频落点；此处仍注入完整契约示例，保证输出结构可解析。
    """
    payload: dict[str, Any] = {
        "shot_list": {
            "target_shots": len(batch["shots"]),
            "shots": [s.model_dump(mode="json") for s in batch["shots"]],
        },
    }
    if batch["scene"] is not None:
        payload["scene"] = batch["scene"]
    return append_output_contract(json.dumps(payload, ensure_ascii=False), contract)


def _pick_fps(results: list[Any]) -> int:
    """从各批输出里取首个合法 target_fps；均无合法值时回退契约缺省。"""
    for res in results:
        fps = as_dict(res).get("target_fps")
        if isinstance(fps, (int, float)) and not isinstance(fps, bool) and fps > 0:
            return int(fps)
    return DEFAULT_FPS


def _merge_beats(results: list[Any]) -> list[dict[str, Any]]:
    """合并各批音频落点：按时间排序 + 同时间点去重（分批各算落点，避免重复堆积）。"""
    unique: dict[float, dict[str, Any]] = {}
    for res in results:
        for beat in as_dict(res).get("audio_beats") or []:
            if not isinstance(beat, dict):
                continue
            event = beat.get("event")
            if not isinstance(event, str) or not event:
                continue
            try:
                time_sec = float(beat.get("time_sec"))
            except (TypeError, ValueError):
                continue
            time_sec = round(time_sec, 3)  # 毫秒精度足够：避免浮点尾差导致同一落点并存
            if time_sec < 0 or time_sec in unique:
                continue
            unique[time_sec] = {"time_sec": time_sec, "event": event}
    return [unique[t] for t in sorted(unique)]


def _merge_editor(shot_list: ShotList, results: list[Any]) -> dict[str, Any]:
    """合并各批 editor 输出：转场/音频取模型值，帧号由代码按全局镜头顺序补全。

    - 不信模型自填的跨批帧号连续性（同 shoot 补 shot_id 的模式）：按 shot_list 全局
      镜头顺序累加「单镜时长 × target_fps」补 start_frame / end_frame，
      total_frames = 实际总和（与 shot_list 镜数、时长对齐）
    - 覆盖校验：任一镜缺时间线条目即明确报错，不静默产出缺镜时间线
      （t1-coffee-envtest「timeline 只出 3 条但 JSON 合法」静默缺失的根治）
    """
    fps = _pick_fps(results)
    entries: dict[str, dict[str, Any]] = {}
    for res in results:
        for item in as_dict(res).get("timeline") or []:
            if not isinstance(item, dict):
                continue
            shot_id = item.get("shot_id")
            if isinstance(shot_id, str) and shot_id:
                entries.setdefault(shot_id, item)  # 同 shot_id 以先出现的批次为准

    missing = [s.shot_id for s in shot_list.shots if s.shot_id not in entries]
    if missing:
        raise RuntimeError(f"editor 分批输出缺失镜头时间线条目：{'、'.join(missing)}")

    timeline: list[dict[str, Any]] = []
    frame = 0
    for shot in shot_list.shots:
        item = entries[shot.shot_id]
        duration_frames = max(1, int(round(float(shot.duration) * fps)))
        transition_in = item.get("transition_in")
        transition_out = item.get("transition_out")
        audio_event = item.get("audio_event")
        timeline.append({
            "shot_id": shot.shot_id,
            "start_frame": frame,                      # 跨批帧号由代码补，连续
            "end_frame": frame + duration_frames,
            "transition_in": transition_in if isinstance(transition_in, str) and transition_in else "Cut",
            "transition_out": transition_out if isinstance(transition_out, str) and transition_out else "Cut",
            "audio_event": audio_event if isinstance(audio_event, str) and audio_event else None,
        })
        frame += duration_frames
    return {
        "target_fps": fps,
        "timeline": timeline,
        "total_frames": frame,                         # = 各镜实际帧数总和
        "audio_beats": _merge_beats(results),
    }


def _validate_blueprint(blueprint: EditingBlueprint, shot_list: ShotList) -> None:
    """产物覆盖/一致性校验（分批合并后的最后一道防线，不一致即报错不静默）。

    - 覆盖：timeline 条数 == shot_list 镜数（防缺镜静默缺失——t1-coffee-envtest
      「timeline 只出 3 条但 JSON 合法」的根治）
    - 连续性：start_frame 逐条等于上一条 end_frame（跨批帧号由代码补，必须连续）
    - 自洽：total_frames == 末条 end_frame（= 各镜时长 × fps 的总和）
    """
    if len(blueprint.timeline) != len(shot_list.shots):
        raise RuntimeError(
            f"editor 时间线覆盖校验失败：timeline {len(blueprint.timeline)} 条 ≠ "
            f"shot_list {len(shot_list.shots)} 镜"
        )
    frame = 0
    for entry in blueprint.timeline:
        if entry.start_frame != frame:
            raise RuntimeError(
                f"editor 时间线帧号不连续：{entry.shot_id} start_frame={entry.start_frame}，"
                f"期望 {frame}"
            )
        frame = entry.end_frame
    if blueprint.total_frames != frame:
        raise RuntimeError(
            f"editor total_frames 与时间线不一致：{blueprint.total_frames} ≠ 末帧 {frame}"
        )


def build_artifact(args: Any, inputs: dict[str, Any], caller: AgentCaller) -> EditingBlueprint:
    """editor：shot_list + script → 按同源场景边界逐场分批排时间线 → 合并补帧号。"""
    shot_list: ShotList = inputs["shoot"]  # type: ignore[assignment]
    script: Script = inputs["script"]  # type: ignore[assignment]

    # 批次边界与 shoot/prompt 同源（逐场；大场按镜组细分）：每批本场镜头子集 + 本场 scene
    batches = _editor_batches(script, shot_list)
    print(f"   🎞 editor 分批：{len(batches)} 批（与 shoot/prompt 同源场景边界）")
    # 注入 EditingBlueprint 契约示例（timeline / audio_beats），约束真实输出格式
    contract = json.dumps(EditingBlueprint.demo().model_dump(mode="json"), ensure_ascii=False)
    result = call_agent_json_batched(
        caller, "editor", "editor",
        [_editor_prompt(batch, contract) for batch in batches],
        merge_fn=lambda results: _merge_editor(shot_list, results),
        model_class=EditingBlueprint,
        count_fn=lambda res: count_batch_key(res, "timeline"),  # dict-safe（可能顶层 list）
    )
    # 覆盖/一致性校验：timeline 条数 == 镜数、帧号连续、total_frames == 末帧
    _validate_blueprint(result, shot_list)
    print(f"   ✅ editor：{len(result.timeline)} 条时间线 / 共 {result.total_frames} 帧")
    return result


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
