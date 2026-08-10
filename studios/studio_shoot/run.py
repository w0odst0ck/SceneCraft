"""Studio Shoot — 分镜站（归入 Agent：director + cinematographer + actor）

输入产物：01_script/script.json（Script）+ 02_art/visual_bible.json（VisualBible）
Agent 调用链：
  1. director        阅读 script + visual_bible → 输出 ShotList 骨架
  2. cinematographer（并行）补摄影参数：机位/焦段/光圈/运镜/布光/景深
  3. actor（并行）    补表演细节：表情/肢体/情绪潜台词/视线
  并行结果按 shot_id 合并进 Shot（补进 lighting / action / emotion 等现有字段，
  不扩展契约，保证下游只读契约字段即可）。
输出产物：<artifacts>/<project_id>/03_shoot/shot_list.json（契约 schemas/shot_list.py::ShotList）
manifest key：shoot ↔ 磁盘目录 03_shoot（映射见 SKILL.md）
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

from schemas.script import Script
from schemas.shot_list import Shot, ShotList
from schemas.visual_bible import VisualBible
from studios import common
from studios.agent_utils import JSONParseError, NoKeyError, AgentCaller, append_output_contract, call_agent_json

STUDIO_KEY = "shoot"
OUTPUT_FILE = "shot_list.json"
INPUTS: list[tuple[str, str, type]] = [
    ("script", "script.json", Script),
    ("art", "visual_bible.json", VisualBible),
]
SOUL_DIR = Path(__file__).parent / "agents"  # director.md / cinematographer.md / actor.md

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


def build_artifact(args: Any, inputs: dict[str, Any], caller: AgentCaller) -> ShotList:
    """director 拆解分镜 → cinematographer + actor 并行细化 → 合并。"""
    script: Script = inputs["script"]  # type: ignore[assignment]
    vb: VisualBible = inputs["art"]  # type: ignore[assignment]

    # 1) director：script + visual_bible → ShotList 骨架（注入 ShotList 契约示例）
    director_in = append_output_contract(
        json.dumps({
            "script": script.model_dump(mode="json"),
            "visual_bible": vb.model_dump(mode="json"),
        }, ensure_ascii=False),
        json.dumps(ShotList.demo().model_dump(mode="json"), ensure_ascii=False),
    )
    shot_list = call_agent_json(caller, "director", "director", director_in, model_class=ShotList)
    print(f"   ✅ director：{len(shot_list.shots)} 个镜头")

    # 2) cinematographer + actor 并行（各自读 shot_list，输出 {shot_id: {...}}；
    #    注入单镜字段契约示例，字段须与 _merge_refinements 消费的一致）
    shot_in = append_output_contract(
        json.dumps({"shot_list": shot_list.model_dump(mode="json")}, ensure_ascii=False),
        _CAMERA_CONTRACT,
    )
    perf_in = append_output_contract(
        json.dumps({"shot_list": shot_list.model_dump(mode="json")}, ensure_ascii=False),
        _PERFORMANCE_CONTRACT,
    )
    cam = call_agent_json(caller, "cinematographer", "cinematographer", shot_in)
    perf = call_agent_json(caller, "actor", "actor", perf_in)
    print(f"   ✅ cinematographer + actor：{len(cam or {})}/{len(perf or {})} 镜细化完成")

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
