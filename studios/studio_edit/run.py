"""Studio Edit — 剪辑站（归入 Agent：editor）

输入产物：03_shoot/shot_list.json（ShotList）+ 01_script/script.json（Script）
输出产物：<artifacts>/<project_id>/05_edit/editing_blueprint.json（契约 schemas/editing_blueprint.py::EditingBlueprint）
manifest key：edit ↔ 磁盘目录 05_edit（映射见 SKILL.md）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.editing_blueprint import EditingBlueprint, TimelineEntry
from schemas.script import Script
from schemas.shot_list import ShotList
from studios import common

STUDIO_KEY = "edit"
OUTPUT_FILE = "editing_blueprint.json"
INPUTS: list[tuple[str, str, type]] = [
    ("shoot", "shot_list.json", ShotList),
    ("script", "script.json", Script),
]

STAGES: list[str] = [
    "TODO_PHASE_B: editor 按 shot_list 排时间线（入出帧 + 转场，对齐 script 情绪曲线）",
    "TODO_PHASE_B: editor 标注音频落点（AudioBeat：鼓点/音效/台词）",
]


def build_skeleton() -> EditingBlueprint:
    """生成输出产物骨架：结构合法，自由文本标注 TODO_PHASE_B 占位。"""
    return EditingBlueprint(
        target_fps=24,
        timeline=[
            TimelineEntry(
                shot_id="SHOT_1",
                start_frame=0,
                end_frame=71,
                transition_in="Cut",
                transition_out="TODO_PHASE_B",
                audio_event="TODO_PHASE_B",
            )
        ],
        total_frames=72,
        audio_beats=[],
    )


def main() -> int:
    args = common.build_parser("Studio Edit：剪辑站（editor）").parse_args()
    project = common.project_dir(args.artifacts_dir, args.project)

    # 1) 加载输入产物（缺 shot_list / script 时友好报错，提示先跑上游）
    inputs = common.load_inputs(project, INPUTS)

    # 2) 打印 Phase B 阶段清单
    print(f"[{STUDIO_KEY}] 本工作室将执行以下阶段（Phase B 调用点）：")
    for i, stage in enumerate(STAGES, 1):
        print(f"  {i}. {stage}")

    # 3) 生成骨架产物并落盘（真实 Agent 逻辑 Phase B 替换）
    artifact = build_skeleton()
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
