"""RenderPlan — 渲染计划产物（Studio Render 输出）

Studio Render 本任务为降级实现（不做真实渲染）：聚合 prompt_list + editing_blueprint，
为每个镜头生成渲染任务卡（provider 默认 "openmontage-pending"），
并粗估渲染成本。Phase D 接入 OpenMontage / bridge 后替换 provider 与状态。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from schemas.artifact import ArtifactBase


class RenderShot(BaseModel):
    """单镜头的渲染任务卡。"""

    shot_id: str = Field(..., description="镜头 ID，须与 shot_list / prompt_list 一致")
    provider: str = Field(default="openmontage-pending", description="渲染服务商（Phase D 接入 OpenMontage）")
    prompt: str = Field(..., description="该镜头使用的视频生成提示词（取自 prompt_list）")
    estimated_cost_usd: float = Field(default=0.0, ge=0, description="该镜头预估渲染成本（美元）")
    status: Literal["pending", "done", "failed"] = Field(
        default="pending", description="渲染状态（本任务一律 pending，Phase D 更新）"
    )


class RenderPlan(ArtifactBase):
    """渲染计划：按镜头聚合的渲染任务清单 + 总预估成本。"""

    project_id: str = Field(..., description="项目 ID，对应 artifacts/<project_id>/")
    shots: list[RenderShot] = Field(..., description="渲染任务列表（每镜头一条）")
    total_estimated_cost_usd: float = Field(..., ge=0, description="全部镜头预估渲染成本合计（美元）")
    notes: str = Field(default="", description="说明（OpenMontage/bridge 接入占位）")

    @classmethod
    def demo(cls) -> "RenderPlan":
        """demo 实例：字段齐全、校验通过。"""
        return cls(
            project_id="demo",
            shots=[
                RenderShot(
                    shot_id="SHOT_1",
                    provider="openmontage-pending",
                    prompt="雨夜霓虹城区，年轻快递员在派件，义体右臂 LED 闪烁。",
                    estimated_cost_usd=0.09,
                    status="pending",
                ),
            ],
            total_estimated_cost_usd=0.09,
            notes="Phase D 接入 OpenMontage/bridge 后替换 provider 与 status。",
        )
