"""Studio Prompt — 提示词站（归入 Agent：prompter）

输入产物：03_shoot/shot_list.json（ShotList）+ 02_art/visual_bible.json（VisualBible）
Agent 调用链：prompter 按 shot_list **逐场分批**生成六要素完整提示词（S2：与 shoot 同源的
  场景边界，保证镜号对应）——景别机位运镜 / 主体 / 动作 / 情绪 / 环境 / 光影画质，
  结合 visual_bible 保证跨镜头一致性；各批 prompts 合并为一份 PromptList（契约不变）
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

STUDIO_KEY = "prompt"
OUTPUT_FILE = "prompt_list.json"
INPUTS: list[tuple[str, str, type]] = [
    ("shoot", "shot_list.json", ShotList),
    ("art", "visual_bible.json", VisualBible),
]
SOUL_DIR = Path(__file__).parent / "agents"  # prompter.md


def _merge_prompt_lists(results: list[Any]) -> dict[str, Any]:
    """合并各批 prompter 输出：prompts 按 shot_id 汇总，model / aspect_ratio 取首个非空值。"""
    demo = PromptList.demo()
    prompts: dict[str, Any] = {}
    model: str | None = None
    aspect_ratio: str | None = None
    for res in results:
        # 类型防护：raw safe_parse_json 可能返回顶层 list（非 dict）→ 取空 dict 跳过
        data = as_dict(res)
        batch_prompts = data.get("prompts")
        if isinstance(batch_prompts, dict):
            prompts.update(batch_prompts)
        model = model or data.get("model")
        aspect_ratio = aspect_ratio or data.get("aspect_ratio")
    return {
        "model": model or demo.model,
        "aspect_ratio": aspect_ratio or demo.aspect_ratio,
        "prompts": prompts,
    }


def build_artifact(args: Any, inputs: dict[str, Any], caller: AgentCaller) -> PromptList:
    """prompter：shot_list + visual_bible → 按同源场景边界逐场分批生成提示词，合并为 PromptList。"""
    shot_list: ShotList = inputs["shoot"]  # type: ignore[assignment]
    vb: VisualBible = inputs["art"]  # type: ignore[assignment]

    # 批次边界与 shoot 站同源（逐场）：每批本场镜头子集 + visual_bible 全量 + PromptList 契约
    scene_groups = group_shots_by_scene(shot_list)
    print(f"   ✍ prompter 分批：{len(scene_groups)} 批（与 shoot 同源场景边界）")
    contract = json.dumps(PromptList.demo().model_dump(mode="json"), ensure_ascii=False)
    batches = [
        append_output_contract(
            json.dumps({
                "shot_list": {
                    "target_shots": len(shots),
                    "shots": [s.model_dump(mode="json") for s in shots],
                },
                "visual_bible": vb.model_dump(mode="json"),
            }, ensure_ascii=False),
            contract,
        )
        for _, shots in scene_groups
    ]
    result = call_agent_json_batched(
        caller, "prompter", "prompter", batches,
        merge_fn=_merge_prompt_lists,
        model_class=PromptList,
        count_fn=lambda res: count_batch_key(res, "prompts"),  # dict-safe（可能顶层 list）
    )
    # 覆盖校验：每个 shot_id 都须有对应提示词（某批漏镜时明确失败，不静默产出缺项产物）
    expected_ids = {s.shot_id for s in shot_list.shots}
    missing = sorted(expected_ids - set(result.prompts))
    if missing:
        raise RuntimeError(f"prompter 分批输出缺失镜头提示词：{missing}")
    return result


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
