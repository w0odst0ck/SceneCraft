"""run_pipeline.py — 端到端一键全链（脚本 → 美术 → 分镜 → 提示词/剪辑 → 渲染，QC 可选）

按依赖顺序依次调用各工作室 run.py（子进程方式，保持各站独立可运行）：
    script → art → shoot → prompt → edit → render  [→ qc（--qc 时）]
- 任一站失败即停，已完成的产物保留（断点续跑可用 --from 从指定站继续）
- --demo 模式走 AgentCaller 演示分支，无 DEEPSEEK_API_KEY 也可跑通全链
- 每站状态与产物路径实时打印
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIOS = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studios.common import STAGE_DIRS  # 01_script … 07_qc 目录映射（与各 run.py 一致）

# 全链依赖顺序（qc 为横切站，默认不参与）
CHAIN = ["script", "art", "shoot", "prompt", "edit", "render"]

# key（manifest 短名）→ 工作室目录名
STUDIO_DIRS = {
    "script": "studio_story",
    "art": "studio_art",
    "shoot": "studio_shoot",
    "prompt": "studio_prompt",
    "edit": "studio_edit",
    "render": "studio_render",
    "qc": "studio_qc",
}

# key → 产物文件（与 common.DEFAULT_FILES 保持一致，仅用于打印产物路径）
OUTPUT_FILES = {
    "script": "script.json",
    "art": "visual_bible.json",
    "shoot": "shot_list.json",
    "prompt": "prompt_list.json",
    "edit": "editing_blueprint.json",
    "render": "render_plan.json",
    "qc": "qc_report.json",
}


def run_studio(key: str, project: str, artifacts_dir: str, concept: str | None,
               demo: bool) -> subprocess.CompletedProcess:
    """以子进程运行一个工作室 run.py，输出透传给父进程。"""
    cmd = [
        sys.executable,
        str(STUDIOS / STUDIO_DIRS[key] / "run.py"),
        "--project", project,
        "--artifacts-dir", artifacts_dir,
    ]
    if key == "script" and concept:
        cmd += ["--concept", concept]
    if demo:
        cmd += ["--demo"]
    return subprocess.run(cmd, cwd=ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SceneCraft 多工作室端到端全链")
    parser.add_argument("--project", required=True, help="项目 ID，如 demo-e2e（对应 artifacts/<project_id>/）")
    parser.add_argument("--concept", default=None, help="用户创意概念（短句；story 站必填）")
    parser.add_argument("--artifacts-dir", default="artifacts/", help="产物仓库根目录（默认 artifacts/）")
    parser.add_argument("--from", dest="from_stage", choices=CHAIN, default="script",
                        help="从指定站开始（断点续跑，默认 script 全链）")
    parser.add_argument("--demo", action="store_true",
                        help="demo 模式：不调用 DeepSeek，使用内置演示输出（无需 API key）")
    parser.add_argument("--qc", action="store_true", help="全链跑完后追加 QC 质检（默认检 script）")
    args = parser.parse_args(argv)

    # 仅当 script 站在本轮待跑链中才强制 --concept（断点续跑 --from 非 script 时无需）
    if args.from_stage == "script" and not args.concept:
        parser.error("--concept 必填（story 站必需），如 --concept \"雨夜便利店的神秘顾客\"")

    print(f"\n{'=' * 60}")
    print(f"🎬 SceneCraft 全链启动：{args.project}")
    print(f"   概念: {args.concept}")
    print(f"   模式: {'Demo（无 API 调用）' if args.demo else 'DeepSeek 真实调用'}")
    print(f"{'=' * 60}\n")

    start = CHAIN.index(args.from_stage)
    pending = CHAIN[start:]
    for key in pending:
        result = run_studio(key, args.project, args.artifacts_dir, args.concept, args.demo)
        if result.returncode != 0:
            print(f"\n❌ 全链中止：{key} 站失败（已完成产物已保留，可用 "
                  f"--from {key} 修复后续跑）")
            return result.returncode
        print(f"✅ {key} 完成")

    if args.qc:
        print("\n▶ QC 质检（检查 script）")
        qc_result = run_studio("qc", args.project, args.artifacts_dir, args.concept, args.demo)
        if qc_result.returncode != 0:
            print("\n❌ QC 失败")
            return qc_result.returncode
        print("✅ qc 完成")

    print(f"\n{'=' * 60}")
    print(f"✅ 全链完成：{args.project}")
    for key in list(pending) + (["qc"] if args.qc else []):
        stage_dir = Path(args.artifacts_dir) / args.project / STAGE_DIRS[key]
        print(f"   📦 {key}: {stage_dir / OUTPUT_FILES[key]}")
    print(f"{'=' * 60}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
