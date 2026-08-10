"""Studio Story — 剧本站（归入 Agent：producer + writer）

输入产物：无（输入为用户概念 concept 字符串，经 --concept 传入）
输出产物：<artifacts>/<project_id>/01_script/script.json（契约 schemas/script.py::Script）
manifest key：script ↔ 磁盘目录 01_script（映射见 SKILL.md）
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许从仓库根目录导入顶层 schemas/（无论从哪个 cwd 调用本脚本）
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.script import Scene, Script
from studios import common

STUDIO_KEY = "script"  # manifest 短名（= 输出 stage 短名）
OUTPUT_FILE = "script.json"
# 输入产物列表：(manifest 短名, 文件名, 契约类) —— 本工作室无上游产物
INPUTS: list[tuple[str, str, type]] = []

# Phase B 的 Agent 调用点占位清单（真实调用在 Phase B 填充）
STAGES: list[str] = [
    "TODO_PHASE_B: producer 接收用户概念，拆解创作目标（类型/时长/镜头数/情绪基调）",
    "TODO_PHASE_B: writer 生成完整剧本（title/logline/scenes/emotional_curve）",
]


def build_skeleton(concept: str) -> Script:
    """生成输出产物骨架：结构合法（可校验通过），自由文本标注 TODO_PHASE_B 占位。"""
    return Script(
        title="TODO_PHASE_B",
        logline=f"TODO_PHASE_B: 用户概念「{concept}」",
        scenes=[
            Scene(
                scene_id="SCENE_1",
                location="TODO_PHASE_B",
                time_of_day="TODO_PHASE_B",
                summary="TODO_PHASE_B（Phase B 由 writer 生成）",
                dialogue="TODO_PHASE_B",
                emotional_arc="TODO_PHASE_B",
                duration_sec=3.0,
            )
        ],
        emotional_curve=["TODO_PHASE_B"],
    )


def main() -> int:
    args = common.build_parser("Studio Story：剧本站（producer + writer）", concept=True).parse_args()
    project = common.project_dir(args.artifacts_dir, args.project)

    # 1) 加载输入产物（本工作室无上游产物，INPUTS 恒为空；缺输入报错逻辑留给有上游的工作室）
    inputs = common.load_inputs(project, INPUTS)

    # 2) 打印 Phase B 阶段清单
    print(f"[{STUDIO_KEY}] 本工作室将执行以下阶段（Phase B 调用点）：")
    for i, stage in enumerate(STAGES, 1):
        print(f"  {i}. {stage}")

    # 3) 生成骨架产物并落盘（真实 Agent 逻辑 Phase B 替换）
    artifact = build_skeleton(args.concept)
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
