"""OpenMontage Bridge — 基础使用示例"""

import json
import sys
from pathlib import Path

# 确保能 import bridge
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openmontage_bridge import Bridge


def demo_discovery():
    """能力发现演示"""
    print("=" * 60)
    print("1. 发现能力")
    print("=" * 60)

    bridge = Bridge()
    report = bridge.discover()

    print(f"\n🔧 共 {len(report.all_tool_names)} 个工具注册")
    print(f"\n🎬 合成引擎: {report.composition_runtimes}")
    print(f"\n📊 能力矩阵:")
    for c in report.capabilities:
        bar = "█" * c["configured"] + "░" * (c["total"] - c["configured"])
        print(f"  {c['capability']:25s} [{bar}] {c['configured']}/{c['total']}")

    if report.runtime_warnings:
        print(f"\n⚠️ 运行时警告:")
        for w in report.runtime_warnings:
            print(f"  • {w}")

    return bridge


def demo_pipelines(bridge):
    """流水线列表演示"""
    print("\n" + "=" * 60)
    print("2. 可用的流水线")
    print("=" * 60)

    pipelines = bridge.list_pipelines()
    for p in pipelines:
        status = "✅" if p.stability == "production" else "🧪"
        print(f"\n  {status} {p.name}")
        print(f"     {p.description[:80]}...")
        print(f"     阶段: {', '.join(p.stages)}")
        print(f"     需人工审批: {', '.join(p.human_approval_gates)}")
    return pipelines


def demo_tool_info(bridge):
    """工具信息查询演示"""
    print("\n" + "=" * 60)
    print("3. 工具信息查询")
    print("=" * 60)

    # 查看几个代表性工具
    for name in ["video_compose", "tts_selector", "image_selector"]:
        info = bridge.tool_info(name)
        if info:
            print(f"\n  📌 {name}")
            print(f"     capability: {info.get('capability')}")
            print(f"     provider: {info.get('provider')}")
            print(f"     status: {info.get('status')}")
            print(f"     best_for: {info.get('best_for', '—')}")


def demo_call_tool(bridge):
    """工具调用演示 (仅可用的工具)"""
    print("\n" + "=" * 60)
    print("4. 工具调用示例")
    print("=" * 60)

    available = bridge.list_available_tools()
    print(f"\n当前可用工具 ({len(available)}):")
    for t in available:
        print(f"  · {t}")

    # 尝试调用一个可用工具 (character_animation tools 是 local-only 可用的)
    char_tools = [t for t in available if "character" in t]
    if char_tools:
        print(f"\n尝试调用: {char_tools[0]}")
        result = bridge.run_tool(char_tools[0], {"action": "list_characters"})
        print(f"  成功: {result.success}")
        if result.data:
            print(f"  数据: {json.dumps(result.data, indent=2, default=str)[:300]}")


def main():
    bridge = demo_discovery()
    demo_pipelines(bridge)
    demo_tool_info(bridge)
    demo_call_tool(bridge)

    print("\n" + "=" * 60)
    print("✅ Bridge 工作正常")
    print("=" * 60)


if __name__ == "__main__":
    main()
