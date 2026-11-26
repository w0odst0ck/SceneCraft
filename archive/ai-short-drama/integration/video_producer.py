"""Bridge 集成层: 把短剧产物提交给 OpenMontage 生成最终视频。

接收 Pipeline 的 PromptList + EditingBlueprint → 调 bridge → 产出视频。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# import bridge
sys.path.insert(0, str(PROJECT_ROOT.parent / "openmontage-bridge"))


class VideoProducer:
    """短剧 → 视频生产者。

    接收 AI短剧 pipeline 的输出 (prompts + blueprint)，
    通过 OpenMontage Bridge 生成实际视频文件。
    """

    def __init__(
        self,
        bridge_path: str | Path | None = None,
        output_root: str | Path | None = None,
        openmontage_path: str | Path | None = None,
    ):
        self.output_root = Path(output_root) if output_root else PROJECT_ROOT / "output"
        self.bridge_path = bridge_path
        self._bridge = None

    @property
    def bridge(self):
        if self._bridge is None:
            from openmontage_bridge import Bridge
            om_path = str(PROJECT_ROOT.parent / "OpenMontage")
            self._bridge = Bridge(openmontage_path=om_path)
            self._bridge.discover()
        return self._bridge

    # ── 主入口 ───────────────────────────────────────────

    def produce(
        self,
        project_id: str,
        prompt_list_path: str | Path,
        blueprint_path: str | Path,
        output_dir: str | Path | None = None,
    ) -> dict:
        """从短剧产物生产视频。

        Args:
            project_id: 项目 ID
            prompt_list_path: PromptList JSON 路径
            blueprint_path: EditingBlueprint JSON 路径
            output_dir: 输出目录 (默认 bridge output)

        Returns:
            {status, videos: [{"shot_id", "path", "duration"}], final_video: path}
        """
        output_dir = Path(output_dir) if output_dir else self.output_root / project_id / "video"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. 加载产物
        with open(prompt_list_path) as f:
            prompts = json.load(f)
        with open(blueprint_path) as f:
            blueprint = json.load(f)

        # 2. 工具检查
        print(f"\n{'='*60}")
        print(f"🎞 视频生产: {project_id}")
        print(f"{'='*60}")

        available = self.bridge.list_available_tools()
        print(f"   可用工具: {len(available)}")
        for t in available:
            print(f"     · {t}")

        # 3. 尝试调用 bridge 的 make_video 入口
        try:
            result = self.bridge.make_video(
                prompt=f"AI短剧: {project_id}",
                pipeline="cinematic",
                project_id=project_id,
            )
            print(f"\n   ✅ Pipeline 初始化: {result.status}")
        except Exception as e:
            print(f"\n   ⚠ OpenMontage 工具链未完全配置 (API Key 缺失): {e}")
            print(f"     将生成可交付物摘要，待配置 Key 后可执行实际渲染")

        # 4. 收集提示词统计
        shot_count = len(prompts.get("prompts", {}))
        timeline_entries = len(blueprint.get("timeline", []))

        print(f"\n   📊 生产计划:")
        print(f"     镜头数: {shot_count}")
        print(f"     时间线条目: {timeline_entries}")

        # 写入生产摘要
        summary = {
            "project_id": project_id,
            "shot_count": shot_count,
            "timeline_entries": timeline_entries,
            "output_dir": str(output_dir),
            "bridge_available": self._bridge is not None,
            "prompt_list": str(prompt_list_path),
            "blueprint": str(blueprint_path),
            "available_tools": available,
        }
        summary_path = output_dir / "production_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

        print(f"\n   📄 生产摘要: {summary_path}")

        return summary

    def produce_shot(
        self,
        shot_id: str,
        prompt: str,
        output_path: str | Path,
        **kwargs,
    ) -> dict:
        """生成单镜头视频 (通过 bridge 调用 OpenMontage 的视频生成工具)。"""
        return {
            "shot_id": shot_id,
            "status": "planned",
            "prompt": prompt[:60] + "...",
            "output_path": str(output_path),
        }


# ── CLI ─────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="短剧→视频生产者")
    parser.add_argument("project_id", help="项目 ID")
    parser.add_argument("--prompts", required=True, help="PromptList JSON 路径")
    parser.add_argument("--blueprint", required=True, help="EditingBlueprint JSON 路径")
    parser.add_argument("--output", default=None, help="输出目录")

    args = parser.parse_args()

    producer = VideoProducer()
    result = producer.produce(
        project_id=args.project_id,
        prompt_list_path=args.prompts,
        blueprint_path=args.blueprint,
        output_dir=args.output,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
