"""EditingBlueprint — 剪辑蓝图产物（Studio Edit 输出）

参考 v1 ai-short-drama/schemas/dual_track.py：
TimelineEntry（镜头入出帧 + 转场）+ AudioBeat（音频落点）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.artifact import ArtifactBase


class TimelineEntry(BaseModel):
    """时间线上的单个镜头切片。"""

    shot_id: str = Field(..., pattern=r"^SHOT_\d+$", description="镜头 ID，须与 shot_list 一致")
    start_frame: int = Field(..., ge=0, description="入点帧号")
    end_frame: int = Field(..., ge=0, description="出点帧号")
    transition_in: str = Field(default="Cut", description="入场转场")
    transition_out: str = Field(default="Cut", description="出场转场")
    audio_event: str | None = Field(default=None, description="入点音频事件（可选）")


class AudioBeat(BaseModel):
    """音频落点。"""

    time_sec: float = Field(..., ge=0, description="落点时间（秒）")
    event: str = Field(..., description="音频事件，如 鼓点 / 音效 / 台词")


class EditingBlueprint(ArtifactBase):
    """剪辑蓝图：帧率 + 时间线 + 总帧数 + 音频落点。"""

    target_fps: int = Field(default=24, gt=0, description="目标帧率")
    timeline: list[TimelineEntry] = Field(..., description="时间线切片列表")
    total_frames: int = Field(..., ge=0, description="总帧数")
    audio_beats: list[AudioBeat] = Field(default_factory=list, description="音频落点列表")

    @classmethod
    def demo(cls) -> "EditingBlueprint":
        """demo 实例：字段齐全、校验通过。"""
        return cls(
            target_fps=24,
            timeline=[
                TimelineEntry(
                    shot_id="SHOT_1",
                    start_frame=0,
                    end_frame=71,
                    transition_in="Cut",
                    transition_out="Fade to black",
                    audio_event="鼓点入点",
                ),
            ],
            total_frames=72,
            audio_beats=[AudioBeat(time_sec=2.0, event="鼓点")],
        )
