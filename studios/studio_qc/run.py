"""Studio QC — 质检站（归入 Agent：critic，横切任意站产物）

输入产物：任意站产物（--input-stage 指定，默认 script；不绑定契约，load_raw 读 JSON 对象）
Agent 调用链：critic 阅读目标站产物 → 输出 QcReport
  （stage 为被检工作室短名 + total_score 0-100 + findings 三级发现；passed 由评分推导）
输出产物：<artifacts>/<project_id>/07_qc/qc_report.json（契约 schemas/qc_report.py::QcReport）
manifest key：qc ↔ 磁盘目录 07_qc（映射见 SKILL.md）
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

from schemas.qc_report import QcReport
from studios import common
from studios.agent_utils import JSONParseError, NoKeyError, AgentCaller, append_output_contract, call_agent_json

STUDIO_KEY = "qc"
OUTPUT_FILE = "qc_report.json"
SOUL_DIR = Path(__file__).parent / "agents"  # critic.md


def build_artifact(args: Any, raw: dict, caller: AgentCaller) -> QcReport:
    """critic：阅读目标站产物 JSON → 输出质检报告。"""
    # 注入 QcReport 契约示例（stage / total_score / findings），约束真实输出格式
    user_prompt = append_output_contract(
        json.dumps({"stage": args.input_stage, "artifact": raw}, ensure_ascii=False),
        json.dumps(QcReport.demo().model_dump(mode="json"), ensure_ascii=False),
    )
    report = call_agent_json(caller, "critic", "critic", user_prompt, model_class=QcReport)
    # 契约要求 stage 为被检工作室短名；Agent 输出与 --input-stage 不一致时给警告（不静默改写）
    if report.stage != args.input_stage:
        print(f"  ⚠ critic 输出的 stage={report.stage!r} 与 --input-stage={args.input_stage!r} 不一致")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = common.build_parser("Studio QC：质检站（critic，可检查任意站产物）")
    parser.add_argument(
        "--input-stage",
        choices=list(common.STAGE_DIRS),
        default="script",
        help="被检查产物的 stage 短名（默认 script）",
    )
    args = parser.parse_args(argv)
    project = common.project_dir(args.artifacts_dir, args.project)

    # 1) 加载目标站产物（任意站，不绑定契约；缺失时友好报错）
    target_path = project / common.STAGE_DIRS[args.input_stage] / common.DEFAULT_FILES[args.input_stage]
    raw = common.load_raw(target_path)

    # 2) critic 质检
    caller = AgentCaller(demo_mode=args.demo, soul_dir=SOUL_DIR)
    artifact = build_artifact(args, raw, caller)
    print(f"   ✅ score={artifact.total_score} / passed={artifact.passed} / "
          f"findings={len(artifact.findings)} 条")

    # 3) 落盘 + 台账
    manifest = common.load_manifest(project)
    upstream = {args.input_stage: common.content_hash(raw)}
    common.mark_start(manifest, STUDIO_KEY, upstream)
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
