"""Studio QC — 质检站（归入 Agent：critic）

输入产物：任意站产物（--input-stage 指定，默认 script）
输出产物：<artifacts>/<project_id>/07_qc/qc_report.json（占位；Phase B 填真实检查项）
manifest key：qc ↔ 磁盘目录 07_qc（映射见 SKILL.md）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from schemas.artifact import ArtifactBase
from studios import common

STUDIO_KEY = "qc"
OUTPUT_FILE = "qc_report.json"

STAGES: list[str] = [
    "TODO_PHASE_B: critic 阅读目标站产物，按严重等级（critical/suggestion/nitpick）输出问题",
    "TODO_PHASE_B: critic 判定 verdict（pass / revise），revise 时退回对应工作室",
]


class QcCheck(BaseModel):
    """单条质检发现。"""

    item: str = Field(default="TODO_PHASE_B", description="检查项")
    severity: str = Field(default="TODO_PHASE_B", description="严重等级：critical / suggestion / nitpick")
    finding: str = Field(default="TODO_PHASE_B", description="发现的问题描述")


class QcReport(ArtifactBase):
    """质检报告（占位契约，Phase B 可扩展）。"""

    target_stage: str = Field(..., description="被检查产物的 stage 短名（如 script）")
    verdict: str = Field(default="TODO_PHASE_B", description="质检结论：pass / revise")
    checks: list[QcCheck] = Field(default_factory=list, description="检查项列表")


def build_skeleton(target_stage: str) -> QcReport:
    """生成占位质检报告：结构合法，内容标注 TODO_PHASE_B。"""
    return QcReport(
        target_stage=target_stage,
        verdict="TODO_PHASE_B",
        checks=[QcCheck(item="TODO_PHASE_B", severity="TODO_PHASE_B", finding="TODO_PHASE_B")],
    )


def main() -> int:
    parser = common.build_parser("Studio QC：质检站（critic，可检查任意站产物）")
    parser.add_argument(
        "--input-stage",
        choices=list(common.STAGE_DIRS),
        default="script",
        help="被检查产物的 stage 短名（默认 script）",
    )
    args = parser.parse_args()
    project = common.project_dir(args.artifacts_dir, args.project)

    # 1) 加载目标站产物（任意站，不绑定契约；缺失时友好报错）
    target_path = project / common.STAGE_DIRS[args.input_stage] / common.DEFAULT_FILES[args.input_stage]
    raw = common.load_raw(target_path)

    # 2) 打印 Phase B 阶段清单
    print(f"[{STUDIO_KEY}] 本工作室将执行以下阶段（Phase B 调用点）：")
    for i, stage in enumerate(STAGES, 1):
        print(f"  {i}. {stage}")
    print(f"  本次检查目标：{args.input_stage}（{target_path}）")

    # 3) 生成占位质检报告并落盘（真实质检逻辑 Phase B 替换）
    artifact = build_skeleton(args.input_stage)
    manifest = common.load_manifest(project)
    upstream = {args.input_stage: common.content_hash(raw)}
    common.mark_start(manifest, STUDIO_KEY, upstream)
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
