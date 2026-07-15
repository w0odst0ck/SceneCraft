"""Dual-Track 产出: 剪辑蓝图 + 提示词列表"""

from typing import Optional
from pydantic import BaseModel, Field


class TimelineEntry(BaseModel):
    shot_id: str
    start_frame: int
    end_frame: int
    transition_in: str = Field("Cut", description="入场转场")
    transition_out: str = Field("Cut", description="出场转场")
    audio_event: Optional[str] = None


class AudioBeat(BaseModel):
    time_sec: float
    event: str


class EditingTimelineBlueprint(BaseModel):
    target_fps: int = 24
    timeline: list[TimelineEntry]
    total_frames: int
    total_duration_sec: float
    audio_beats: list[AudioBeat] = []


class ShotPrompt(BaseModel):
    shot_id: str
    prompt: str = Field(..., description="六要素完整提示词")
    negative_prompt: Optional[str] = ""
    model: str = "Kling 2.0"
    aspect_ratio: str = "16:9"


class PromptList(BaseModel):
    model: str
    aspect_ratio: str
    prompts: dict[str, ShotPrompt]  # key = shot_id


class EditingBlueprint(BaseModel):
    prompts: PromptList
    timeline: EditingTimelineBlueprint
