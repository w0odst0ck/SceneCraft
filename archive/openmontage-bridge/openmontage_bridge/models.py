"""Data models for OpenMontage Bridge."""

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class ToolStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


@dataclass
class ToolResult:
    """Result from a single tool call."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    tool_name: str = ""
    cost_usd: float = 0.0


@dataclass
class PipelineInfo:
    """Information about a registered pipeline."""
    name: str
    description: str
    stability: str
    stages: list[str]
    human_approval_gates: list[str]


@dataclass
class PipelineStatus:
    """Status of a running/completed pipeline."""
    project_id: str
    pipeline_name: str
    current_stage: str
    status: str  # completed | failed | awaiting_human | in_progress
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoRequest:
    """High-level video production request."""
    prompt: str
    pipeline: str = "animated-explainer"
    duration_seconds: int = 60
    style: str = "flat-motion-graphics"
    resolution: str = "1920x1080"
    output_dir: str = ""
    budget_usd: float = 2.0


@dataclass
class DiscoveryReport:
    """Summary of discovered capabilities."""
    composition_runtimes: dict[str, bool] = field(default_factory=dict)
    capabilities: list[dict] = field(default_factory=list)
    setup_offers: list[dict] = field(default_factory=list)
    runtime_warnings: list[str] = field(default_factory=list)
    all_tool_names: list[str] = field(default_factory=list)
    project_root: str = ""
