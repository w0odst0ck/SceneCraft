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
# 两环境公共描述函数（供 main 启动提示用；run_pipeline 以子进程逐站调 run.py，env 提示仅防跑错环境）
from studios.agent_utils import describe_environment

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
               demo: bool, material_tags: str | None = None,
               render: bool = False, render_limit: int | None = None) -> subprocess.CompletedProcess:
    """以子进程运行一个工作室 run.py，输出透传给父进程。"""
    cmd = [
        sys.executable,
        str(STUDIOS / STUDIO_DIRS[key] / "run.py"),
        "--project", project,
        "--artifacts-dir", artifacts_dir,
    ]
    if key == "script" and concept:
        cmd += ["--concept", concept]
        if material_tags:  # 素材注入仅 story 站消费（story-materials pick）
            cmd += ["--material-tags", material_tags]
    if key == "render":  # 真实渲染开关仅 render 站消费（镜像 --material-tags 的转发写法）
        if render:
            cmd += ["--render"]
        if render_limit is not None:
            cmd += ["--render-limit", str(render_limit)]
    if demo:
        cmd += ["--demo"]
    return subprocess.run(cmd, cwd=ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SceneCraft 多工作室端到端全链")
    parser.add_argument("--project", required=True, help="项目 ID，如 demo-e2e（对应 artifacts/<project_id>/）")
    parser.add_argument("--concept", default=None, help="用户创意概念（短句；story 站必填）")
    parser.add_argument("--material-tags", default=None,
                        help="story-materials 素材卡 tags（逗号分隔；仅 story 站注入，未命中不影响流程）")
    parser.add_argument("--artifacts-dir", default="artifacts/", help="产物仓库根目录（默认 artifacts/）")
    parser.add_argument("--from", dest="from_stage", choices=CHAIN, default="script",
                        help="从指定站开始（断点续跑，默认 script 全链）")
    parser.add_argument("--demo", action="store_true",
                        help="demo 模式：不调用 DeepSeek，使用内置演示输出（无需 API key）")
    parser.add_argument("--qc", action="store_true", help="全链跑完后追加 QC 质检（默认检 script）")
    parser.add_argument("--render", action="store_true",
                        help="render 站真实本地渲染（ComfyUI + LTX-Video 2B）；默认只出渲染计划")
    parser.add_argument("--render-limit", type=int, default=None,
                        help="render 站仅渲染前 N 镜（其余保持 pending）；需配合 --render")
    args = parser.parse_args(argv)

    # 两环境启动提示（run_pipeline 以子进程逐站调 run.py，env 不跨进程共享——
    # 各站 run.py 各自读 env（现状）；此处打印仅作提示，杜绝跑错环境）
    env, backend, model = describe_environment()
    print(f"环境: {env} → 后端 {backend}（模型 {model}）")

    # 仅当 script 站在本轮待跑链中才强制 --concept（断点续跑 --from 非 script 时无需）
    if args.from_stage == "script" and not args.concept:
        parser.error("--concept 必填（story 站必需），如 --concept \"雨夜便利店的神秘顾客\"")

    print(f"\n{'=' * 60}")
    print(f"🎬 SceneCraft 全链启动：{args.project}")
    print(f"   概念: {args.concept}")
    print(f"   素材: {args.material_tags or '（未指定）'}")
    print(f"   模式: {'Demo（无 API 调用）' if args.demo else 'DeepSeek 真实调用'}")
    print(f"   渲染: {'真实本地渲染（LTX-Video 2B）' if args.render else '仅出渲染计划（不渲染）'}"
          + (f"，限前 {args.render_limit} 镜" if args.render and args.render_limit else ""))
    print(f"{'=' * 60}\n")

    start = CHAIN.index(args.from_stage)
    pending = CHAIN[start:]
    for key in pending:
        result = run_studio(key, args.project, args.artifacts_dir, args.concept, args.demo,
                            args.material_tags, args.render, args.render_limit)
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
