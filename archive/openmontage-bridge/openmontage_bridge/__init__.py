"""OpenMontage Bridge — 隔离层，通过 Python API 调用 OpenMontage 能力。

使用方式：
    from openmontage_bridge import Bridge
    bridge = Bridge(openmontage_path="projects/OpenMontage")
    bridge.discover()
    summary = bridge.provider_menu_summary()
    result = bridge.run_tool("tts_selector", {"text": "hello", ...})
"""

from .bridge import Bridge
from .models import (
    DiscoveryReport,
    ToolResult,
    PipelineInfo,
    PipelineStatus,
    VideoRequest,
)

__all__ = [
    "Bridge",
    "DiscoveryReport",
    "ToolResult",
    "PipelineInfo",
    "PipelineStatus",
    "VideoRequest",
]
