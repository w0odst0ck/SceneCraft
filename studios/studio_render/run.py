"""Studio Render — 渲染站（降级实现：本任务不做真实渲染）

输入产物：04_prompt/prompt_list.json（PromptList）+ 05_edit/editing_blueprint.json（EditingBlueprint）
实现：聚合 prompt_list + editing_blueprint → RenderPlan
  - 每镜头一条渲染任务卡（provider 默认 "openmontage-pending"、status "pending"）
  - estimated_cost_usd 按镜头时长粗估（常量 COST_PER_SEC_USD）
  - notes 说明 Phase D 接入 OpenMontage / bridge 后执行真实渲染
输出产物：<artifacts>/<project_id>/06_render/render_plan.json
  （契约 schemas/render_plan.py::RenderPlan）
manifest key：render ↔ 磁盘目录 06_render（映射见 SKILL.md）
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.editing_blueprint import EditingBlueprint
from schemas.prompt_list import PromptList
from schemas.render_plan import RenderPlan, RenderShot
from studios import common
from studios.agent_utils import NoKeyError

STUDIO_KEY = "render"
OUTPUT_FILE = "render_plan.json"
INPUTS: list[tuple[str, str, type]] = [
    ("prompt", "prompt_list.json", PromptList),
    ("edit", "editing_blueprint.json", EditingBlueprint),
]

# 渲染成本粗估：按镜头时长 × 单价（美元/秒，示例值，Phase D 按实际服务商计价修正）
COST_PER_SEC_USD = 0.003

RENDER_NOTES = (
    "Phase D 接入 OpenMontage / openmontage-bridge：将本计划的 shots 逐镜提交真实渲染，"
    "provider 由 openmontage-pending 替换为实际服务商，status 由 pending 更新为 done/failed。"
)


def build_artifact(args: Any, inputs: dict[str, Any]) -> RenderPlan:
    """聚合 prompt_list + editing_blueprint → RenderPlan（降级实现，无 Agent 调用）。"""
    prompt_list: PromptList = inputs["prompt"]  # type: ignore[assignment]
    edit_bp: EditingBlueprint = inputs["edit"]  # type: ignore[assignment]
    fps = edit_bp.target_fps or 24

    shots: list[RenderShot] = []
    for entry in edit_bp.timeline:
        # 帧号闭区间语义（含端点）：镜长 = end - start + 1
        duration = max(0.0, (entry.end_frame - entry.start_frame + 1) / fps)
        sp = prompt_list.prompts.get(entry.shot_id)
        shots.append(RenderShot(
            shot_id=entry.shot_id,
            provider="openmontage-pending",
            prompt=sp.prompt if sp else "",
            estimated_cost_usd=round(duration * COST_PER_SEC_USD, 4),
            status="pending",
        ))
    total = round(sum(s.estimated_cost_usd for s in shots), 4)
    return RenderPlan(
        project_id=args.project,
        shots=shots,
        total_estimated_cost_usd=total,
        notes=RENDER_NOTES,
    )


def main(argv: list[str] | None = None) -> int:
    args = common.build_parser("Studio Render：渲染站（降级实现，无 Agent 调用）").parse_args(argv)
    project = common.project_dir(args.artifacts_dir, args.project)

    # 加载输入产物（缺 prompt_list / editing_blueprint 时友好报错，提示先跑上游）
    inputs = common.load_inputs(project, INPUTS)

    artifact = build_artifact(args, inputs)

    manifest = common.load_manifest(project)
    common.mark_start(manifest, STUDIO_KEY, common.upstream_hashes(inputs))
    out_path = common.write_artifact(project, STUDIO_KEY, OUTPUT_FILE, artifact)
    common.mark_done(manifest, STUDIO_KEY, artifact)
    manifest.studios[STUDIO_KEY].cost_usd = 0.0  # 本任务无 Agent 调用
    common.save_manifest(project, manifest)

    print(f"输出产物：{out_path}")
    print(f"项目台账：{project / 'manifest.json'}")
    print(f"渲染计划：{len(artifact.shots)} 镜 / 预估成本 ${artifact.total_estimated_cost_usd:.4f}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (common.InputError, common.HumanEditError, NoKeyError,
            ValidationError, RuntimeError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)
