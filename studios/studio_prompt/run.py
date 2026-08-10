"""Studio Prompt — 提示词站（归入 Agent：prompter）

输入产物：03_shoot/shot_list.json（ShotList）+ 02_art/visual_bible.json（VisualBible）
Agent 调用链：prompter 按 shot_list 每镜生成六要素完整提示词
  （景别机位运镜 / 主体 / 动作 / 情绪 / 环境 / 光影画质），结合 visual_bible 保证跨镜头一致性
输出产物：<artifacts>/<project_id>/04_prompt/prompt_list.json（契约 schemas/prompt_list.py::PromptList）
manifest key：prompt ↔ 磁盘目录 04_prompt（映射见 SKILL.md）
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

from schemas.prompt_list import PromptList
from schemas.shot_list import ShotList
from schemas.visual_bible import VisualBible
from studios import common
from studios.agent_utils import JSONParseError, NoKeyError, AgentCaller, append_output_contract, call_agent_json

STUDIO_KEY = "prompt"
OUTPUT_FILE = "prompt_list.json"
INPUTS: list[tuple[str, str, type]] = [
    ("shoot", "shot_list.json", ShotList),
    ("art", "visual_bible.json", VisualBible),
]
SOUL_DIR = Path(__file__).parent / "agents"  # prompter.md


def build_artifact(args: Any, inputs: dict[str, Any], caller: AgentCaller) -> PromptList:
    """prompter：shot_list + visual_bible → 每镜六要素提示词。"""
    shot_list: ShotList = inputs["shoot"]  # type: ignore[assignment]
    vb: VisualBible = inputs["art"]  # type: ignore[assignment]
    # 注入 PromptList 契约示例（prompts 映射结构），约束真实输出格式
    user_prompt = append_output_contract(
        json.dumps({
            "shot_list": shot_list.model_dump(mode="json"),
            "visual_bible": vb.model_dump(mode="json"),
        }, ensure_ascii=False),
        json.dumps(PromptList.demo().model_dump(mode="json"), ensure_ascii=False),
    )
    return call_agent_json(caller, "prompter", "prompter", user_prompt, model_class=PromptList)


def main(argv: list[str] | None = None) -> int:
    args = common.build_parser("Studio Prompt：提示词站（prompter）").parse_args(argv)
    project = common.project_dir(args.artifacts_dir, args.project)

    # 加载输入产物（缺 shot_list / visual_bible 时友好报错，提示先跑上游）
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
