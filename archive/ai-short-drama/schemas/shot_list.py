"""Director → 全系统: Shot List + 单镜头参数卡"""

from typing import Optional
from pydantic import BaseModel, Field

class ShotParameterCard(BaseModel):
    shot_id: str = Field(..., pattern=r"^SHOT_\d+$")
    scene_id: str = Field(..., pattern=r"^SCENE_\d+$")
    duration_sec: float = Field(..., gt=0)
    subject: str = Field(..., description="主体描述")
    action: str = Field(..., description="动作描述")
    emotion: str = Field(..., description="情绪状态")
    environment: str = Field(..., description="环境描述")
    lighting: str = Field(..., description="光影方案")
    camera_angle: str = Field(..., description="机位角度")
    camera_movement: str = Field(..., description="运镜轨迹")
    focal_length: str = Field("50mm", description="焦段")
    narrative_purpose: str = Field(..., description="本镜头叙事目的")

class ShotList(BaseModel):
    target_shots: int
    shots: list[ShotParameterCard]
    total_duration_sec: float
