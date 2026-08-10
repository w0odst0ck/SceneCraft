"""Studio Art — 美术站（归入 Agent：art_director）

输入产物：01_script/script.json（Script）
Agent 调用链：art_director 阅读 script → 输出 VisualBible
  （color_palette / material_style / lighting_style / character_designs / art_notes）
输出产物：<artifacts>/<project_id>/02_art/visual_bible.json（契约 schemas/visual_bible.py::VisualBible）
manifest key：art ↔ 磁盘目录 02_art（映射见 SKILL.md）
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
from schemas.visual_bible import VisualBible
from studios import common
from studios.agent_utils import JSONParseError, NoKeyError, AgentCaller, append_output_contract, call_agent_json

STUDIO_KEY = "art"
OUTPUT_FILE = "visual_bible.json"
INPUTS: list[tuple[str, str, type]] = [("script", "script.json", Script)]
SOUL_DIR = Path(__file__).parent / "agents"  # art_director.md


def build_artifact(args: Any, inputs: dict[str, Any], caller: AgentCaller) -> VisualBible:
    """art_director：阅读 script，定义整剧视觉语言（色彩/材质/光照/角色造型）。"""
    script: Script = inputs["script"]  # type: ignore[assignment]
    # 注入 VisualBible 契约示例，约束真实输出格式（色彩/材质/光照/角色造型/备注）
    user_prompt = append_output_contract(
        json.dumps({"script": script.model_dump(mode="json")}, ensure_ascii=False),
        json.dumps(VisualBible.demo().model_dump(mode="json"), ensure_ascii=False),
    )
    return call_agent_json(caller, "art_director", "art_director", user_prompt, model_class=VisualBible)


def main(argv: list[str] | None = None) -> int:
    args = common.build_parser("Studio Art：美术站（art_director）").parse_args(argv)
    project = common.project_dir(args.artifacts_dir, args.project)

    # 加载输入产物（缺 script.json 时友好报错，提示先跑 Studio Story）
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
