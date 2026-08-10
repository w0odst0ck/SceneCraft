"""Studio Shoot — 分镜站（归入 Agent：director, cinematographer, actor）

输入产物：01_script/script.json（Script）+ 02_art/visual_bible.json（VisualBible）
输出产物：<artifacts>/<project_id>/03_shoot/shot_list.json（契约 schemas/shot_list.py::ShotList）
manifest key：shoot ↔ 磁盘目录 03_shoot（映射见 SKILL.md）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.script import Script
from schemas.shot_list import Shot, ShotList
from schemas.visual_bible import VisualBible
from studios import common

STUDIO_KEY = "shoot"
OUTPUT_FILE = "shot_list.json"
INPUTS: list[tuple[str, str, type]] = [
    ("script", "script.json", Script),
    ("art", "visual_bible.json", VisualBible),
]

STAGES: list[str] = [
    "TODO_PHASE_B: director 按 script 拆解镜头序列（覆盖全部剧情节点）",
    "TODO_PHASE_B: cinematographer 为每镜标注机位角度 / 运镜 / 焦段 / 光影",
    "TODO_PHASE_B: actor 为每镜补动作与情绪表演细节",
]


def build_skeleton() -> ShotList:
    """生成输出产物骨架：结构合法，自由文本标注 TODO_PHASE_B 占位。"""
    return ShotList(
        target_shots=1,
        shots=[
            Shot(
                shot_id="SHOT_1",
                scene_id="SCENE_1",
                duration=3.0,
                subject="TODO_PHASE_B",
                action="TODO_PHASE_B",
                emotion="TODO_PHASE_B",
                environment="TODO_PHASE_B",
                lighting="TODO_PHASE_B",
                camera_angle="TODO_PHASE_B",
                camera_movement="TODO_PHASE_B",
                focal_length="50mm",
                narrative_purpose="TODO_PHASE_B",
            )
        ],
    )


def main() -> int:
    args = common.build_parser("Studio Shoot：分镜站（director + cinematographer + actor）").parse_args()
    project = common.project_dir(args.artifacts_dir, args.project)

    # 1) 加载输入产物（缺 script / visual_bible 时友好报错，提示先跑上游）
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
