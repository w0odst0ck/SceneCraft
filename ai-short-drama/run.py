"""AI短剧多Agent制作工厂 — 一键运行入口"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestration.pipeline import ShortDramaPipeline
from integration.video_producer import VideoProducer


def run_short_drama(
    concept: str,
    project_id: str | None = None,
    produce_video: bool = False,
) -> dict:
    """一键运行：短剧制作 + 可选视频生成。

    Args:
        concept: 创意概念
        project_id: 项目ID (自动生成)
        produce_video: 是否尝试生成视频 (需 API Key)

    Returns:
        交付物路径字典
    """
    # 1. 多 Agent 创意生产
    pipeline = ShortDramaPipeline(concept=concept, project_id=project_id)
    deliverables = pipeline.run()

    # 2. 可选：提交给 OpenMontage 生成视频
    if produce_video:
        prompts_path = deliverables.get("prompts_for_ai_video")
        blueprint_path = deliverables.get("editing_blueprint")
        if prompts_path and blueprint_path:
            producer = VideoProducer()
            producer.produce(
                project_id=pipeline.project_id,
                prompt_list_path=prompts_path,
                blueprint_path=blueprint_path,
            )
        else:
            print("⚠ 缺少 prompts 或 blueprint，跳过视频生成")

    return deliverables


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI短剧制作工厂")
    parser.add_argument("concept", nargs="?", default=None,
                        help="创意概念 (不传则交互)")
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--render", action="store_true",
                        help="完成后尝试通过 OpenMontage 渲染视频")
    args = parser.parse_args()

    concept = args.concept
    if not concept:
        concept = input("请输入短剧创意概念: ").strip()
        if not concept:
            concept = "赛博朋克短剧：一个快递员发现自己的义体在秘密收集记忆数据"

    run_short_drama(
        concept=concept,
        project_id=args.project_id,
        produce_video=args.render,
    )


if __name__ == "__main__":
    main()
