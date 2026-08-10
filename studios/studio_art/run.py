"""Studio Art — 美术站（归入 Agent：art_director）

输入产物：01_script/script.json（Script）
输出产物：<artifacts>/<project_id>/02_art/visual_bible.json（契约 schemas/visual_bible.py::VisualBible）
manifest key：art ↔ 磁盘目录 02_art（映射见 SKILL.md）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.script import Script
from schemas.visual_bible import CharacterDesign, ColorPalette, VisualBible
from studios import common

STUDIO_KEY = "art"
OUTPUT_FILE = "visual_bible.json"
INPUTS: list[tuple[str, str, type]] = [("script", "script.json", Script)]

STAGES: list[str] = [
    "TODO_PHASE_B: art_director 阅读 script，定义色彩基调 / 材质 / 光照（与情绪曲线对齐）",
    "TODO_PHASE_B: art_director 为每个角色编写造型设计（appearance/costume/color_key）",
]


def build_skeleton() -> VisualBible:
    """生成输出产物骨架：结构合法，自由文本标注 TODO_PHASE_B 占位。"""
    return VisualBible(
        color_palette=ColorPalette(
            primary="TODO_PHASE_B",
            secondary="TODO_PHASE_B",
            accent="TODO_PHASE_B",
            mood="TODO_PHASE_B",
        ),
        material_style="TODO_PHASE_B",
        lighting_style="TODO_PHASE_B",
        character_designs=[
            CharacterDesign(
                character="TODO_PHASE_B",
                appearance="TODO_PHASE_B",
                costume="TODO_PHASE_B",
                color_key="TODO_PHASE_B",
            )
        ],
        art_notes=["TODO_PHASE_B"],
    )


def main() -> int:
    args = common.build_parser("Studio Art：美术站（art_director）").parse_args()
    project = common.project_dir(args.artifacts_dir, args.project)

    # 1) 加载输入产物（缺 script.json 时友好报错，提示先跑 Studio Story）
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
