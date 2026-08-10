"""Studio Render — 渲染站（bridge 占位，Phase B 接 openmontage-bridge）

输入产物：04_prompt/prompt_list.json（PromptList）+ 05_edit/editing_blueprint.json（EditingBlueprint）
输出产物：<artifacts>/<project_id>/06_render/video_placeholder.json（占位；Phase B 渲染为真实视频产物）
manifest key：render ↔ 磁盘目录 06_render（映射见 SKILL.md）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import Field

from schemas.artifact import ArtifactBase
from schemas.editing_blueprint import EditingBlueprint
from schemas.prompt_list import PromptList
from studios import common

STUDIO_KEY = "render"
OUTPUT_FILE = "video_placeholder.json"
INPUTS: list[tuple[str, str, type]] = [
    ("prompt", "prompt_list.json", PromptList),
    ("edit", "editing_blueprint.json", EditingBlueprint),
]

STAGES: list[str] = [
    "TODO_PHASE_B: 汇总 prompt_list + editing_blueprint，组装渲染任务清单",
    "TODO_PHASE_B: 调用 openmontage-bridge（bridge.py）逐镜渲染，输出真实视频产物",
]


class RenderPlaceholder(ArtifactBase):
    """视频产物占位（Phase B 由 openmontage-bridge 渲染后替换为真实视频）。"""

    status: str = Field(default="TODO_PHASE_B", description="渲染状态")
    message: str = Field(default="TODO_PHASE_B: Phase B 接入 openmontage-bridge", description="说明")
    input_prompt_count: int = Field(ge=0, description="消费的提示词条数")
    timeline_frames: int = Field(ge=0, description="消费的时间线总帧数")


def build_skeleton(prompt_count: int, timeline_frames: int) -> RenderPlaceholder:
    """生成占位产物：真实统计来自输入产物，其余标注 TODO_PHASE_B。"""
    return RenderPlaceholder(
        status="TODO_PHASE_B",
        message="TODO_PHASE_B: Phase B 接入 openmontage-bridge 渲染视频",
        input_prompt_count=prompt_count,
        timeline_frames=timeline_frames,
    )


def main() -> int:
    args = common.build_parser("Studio Render：渲染站（bridge 占位）").parse_args()
    project = common.project_dir(args.artifacts_dir, args.project)

    # 1) 加载输入产物（缺 prompt_list / editing_blueprint 时友好报错，提示先跑上游）
    inputs = common.load_inputs(project, INPUTS)
    prompt_list: PromptList = inputs["prompt"]  # type: ignore[assignment]
    edit_bp: EditingBlueprint = inputs["edit"]  # type: ignore[assignment]

    # 2) 打印 Phase B 阶段清单
    print(f"[{STUDIO_KEY}] 本工作室将执行以下阶段（Phase B 调用点）：")
    for i, stage in enumerate(STAGES, 1):
        print(f"  {i}. {stage}")

    # 3) 生成占位产物并落盘（真实渲染逻辑 Phase B 替换）
    artifact = build_skeleton(len(prompt_list.prompts), edit_bp.total_frames)
    manifest = common.load_manifest(project)
    common.mark_start(manifest, STUDIO_KEY, common.upstream_hashes(inputs))
    out_path = common.write_artifact(project, STUDIO_KEY, OUTPUT_FILE, artifact)
    common.mark_done(manifest, STUDIO_KEY, artifact)
    common.save_manifest(project, manifest)

    # 4) 打印产物路径
    print(f"输出产物：{out_path}")
    print(f"项目台账：{project / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except common.InputError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)
