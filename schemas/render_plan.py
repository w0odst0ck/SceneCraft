"""RenderPlan — 渲染计划产物（Studio Render 输出）

Studio Render 默认仍是降级实现（不做真实渲染）：聚合 prompt_list + editing_blueprint，
为每个镜头生成渲染任务卡（provider 默认 "openmontage-pending"），并粗估渲染成本。

S4 起支持真实本地渲染（studio_render/run.py --render，ComfyUI + LTX-Video 2B）：
此时 provider 置为 "comfyui-ltxv"，status 按渲染结果置 done/failed，
并回填产物路径 / 实际片长 / 峰值显存 / 失败原因（见 RenderShot 的 optional 字段）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from schemas.artifact import ArtifactBase


class RenderShot(BaseModel):
    """单镜头的渲染任务卡。

    默认（未接真实渲染）：provider="openmontage-pending"、status="pending"，
    四个 optional 字段均为 None；S4 真实渲染（--render）后由 render 站回填。
    """

    shot_id: str = Field(..., description="镜头 ID，须与 shot_list / prompt_list 一致")
    provider: str = Field(
        default="openmontage-pending",
        description='渲染服务商；"comfyui-ltxv" 表示本地真实渲染（ComfyUI + LTX-Video 2B）',
    )
    prompt: str = Field(..., description="该镜头使用的视频生成提示词（取自 prompt_list）")
    estimated_cost_usd: float = Field(default=0.0, ge=0, description="该镜头预估渲染成本（美元）")
    status: Literal["pending", "done", "failed"] = Field(
        default="pending", description="渲染状态：pending 未渲染 / done 成功 / failed 失败（见 error）"
    )
    output_file: str | None = Field(
        default=None, description="渲染产物路径（相对 artifacts 根目录），未渲染为 None"
    )
    duration_sec: float | None = Field(
        default=None, ge=0, description="该镜片长（秒，= 帧数 / 帧率），未渲染为 None"
    )
    peak_vram_mb: int | None = Field(
        default=None, ge=0, description="渲染峰值显存（MiB），未渲染/取不到为 None"
    )
    error: str | None = Field(
        default=None, description="失败原因（失败时不静默），成功/未渲染为 None"
    )


class RenderPlan(ArtifactBase):
    """渲染计划：按镜头聚合的渲染任务清单 + 总预估成本。

    provider/status 与 RenderShot 同语义：默认全 pending 占位；
    --render 真实渲染后部分/全部镜头变为 comfyui-ltxv + done/failed。
    """

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
