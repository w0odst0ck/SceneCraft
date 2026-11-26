"""Writer → Director: Script (完整剧本)"""
from typing import Optional
from pydantic import BaseModel, Field

class Scene(BaseModel):
    scene_id: str = Field(..., pattern=r"^SCENE_\d+$")
    location: str
    time_of_day: str
    summary: str = Field(..., description="本场概要")
    dialogue: Optional[str] = None
    emotional_arc: str
    duration_sec: float

class Script(BaseModel):
    title: str
    logline: str
    scenes: list[Scene]
    total_duration_sec: float
    emotional_curve: list[str] = Field(..., description="全剧情绪曲线标注")
