"""Manifest — 项目产物索引 + 各工作室状态（非产物，不继承 ArtifactBase）

manifest.json 是每个项目的「总台账」：
- 记录 7 个工作室的运行状态（pending / running / done / failed / manual_edited）
- 记录各工作室产物的 version / output_hash / upstream_hash / 成本 / 起止时间
- current_focus 表示当前焦点工作室，支撑断点续跑定位下一步
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StudioStatus(BaseModel):
    """单个工作室在 manifest 中的状态记录。"""

    status: Literal["pending", "running", "done", "failed", "manual_edited"] = Field(
        default="pending", description="工作室状态"
    )
    version: int = Field(default=0, ge=0, description="已产出产物版本号（0 = 尚未产出）")
    edited_by: Literal["ai", "human"] = Field(
        default="ai", description="最近一次产出方（human = 人工修改过，AI 重跑须保护）"
    )
    output_hash: str | None = Field(default=None, description="最近一次产出的内容 hash")
    upstream_hash: dict[str, str] = Field(
        default_factory=dict, description="本次产出所消费的上游产物 hash（血缘）"
    )
    cost_usd: float | None = Field(default=None, description="本工作室累计成本（美元）")
    started_at: str | None = Field(default=None, description="最近一次开始运行时间（ISO 8601）")
    finished_at: str | None = Field(default=None, description="最近一次完成时间（ISO 8601）")


class Manifest(BaseModel):
    """项目级产物索引。"""

    project_id: str = Field(..., description="项目 ID，对应 artifacts/<project_id>/ 目录")
    created_at: str = Field(..., description="项目创建时间（ISO 8601）")
    studios: dict[str, StudioStatus] = Field(
        default_factory=dict,
        description="各工作室状态，key 为工作室短名（script/art/shoot/prompt/edit/render/qc）",
    )
    current_focus: str | None = Field(
        default=None, description="当前焦点工作室短名；断点续跑时从这里继续"
    )
