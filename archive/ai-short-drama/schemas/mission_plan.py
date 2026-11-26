"""Producer → 全系统: Mission Plan (任务拆解书)"""
from typing import Optional
from pydantic import BaseModel, Field

class MissionPlan(BaseModel):
    concept: str = Field(..., description="用户输入的创意概念")
    genre: str = Field("科幻", description="短剧类型")
    target_duration_sec: int = Field(120, description="目标总时长(秒)")
    target_shots: int = Field(20, description="目标镜头数")
    tone: str = Field("cinematic", description="情绪基调")
    aspect_ratio: str = Field("16:9", description="画幅比例")
    fps: int = Field(24, description="帧率")
    max_iterations: int = Field(3, description="最大迭代次数")
