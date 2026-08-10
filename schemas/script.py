"""Script — 剧本产物（Studio Story 输出）

复用 v1 ai-short-drama/schemas/script.py 的字段思路
（title / logline / scenes / emotional_curve），顶层独立实现，字段可扩展。

Phase B.1 契约修正：真实 DeepSeek 输出剧本对白为多轮对话结构
（[{"speaker": "...", "line": "..."}]），原 `str` 单串类型与真实输出不符，
故将 Scene.dialogue 由 `str | None` 改为 `list[DialogueLine] | None`。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.artifact import ArtifactBase


class DialogueLine(BaseModel):
    """单句对白：说话人 + 台词。"""

    speaker: str = Field(..., description="说话人（角色名）")
    line: str = Field(..., description="台词内容")


class Scene(BaseModel):
    """单场戏。"""

    scene_id: str = Field(..., pattern=r"^SCENE_\d+$", description="场次 ID，如 SCENE_1")
    location: str = Field(..., description="场景地点")
    time_of_day: str = Field(..., description="时间段（如 夜晚 / 黄昏）")
    summary: str = Field(..., description="本场概要")
    dialogue: list[DialogueLine] | None = Field(
        default=None, description="本场多轮对白列表（可选；每轮为说话人 + 台词）"
    )
    emotional_arc: str = Field(..., description="本场情绪走向")
    duration_sec: float = Field(..., gt=0, description="本场预估时长（秒）")


class Script(ArtifactBase):
    """完整剧本：title + logline + scenes + 全剧情绪曲线。"""

    title: str = Field(..., description="剧名")
    logline: str = Field(..., description="一句话故事梗概")
    scenes: list[Scene] = Field(..., description="场次列表")
    emotional_curve: list[str] = Field(..., description="全剧情绪曲线标注（按场次推进）")

    @classmethod
    def demo(cls) -> "Script":
        """demo 实例：字段齐全、校验通过，供测试与 Phase B 骨架参考。"""
        return cls(
            title="赛博快递员",
            logline="一名赛博快递员发现自己植入的义体在偷偷收集记忆。",
            scenes=[
                Scene(
                    scene_id="SCENE_1",
                    location="霓虹城区",
                    time_of_day="夜晚",
                    summary="快递员在雨夜派件时发现义体异常。",
                    dialogue=[
                        DialogueLine(speaker="义体", line="你的记忆…是我的。"),
                        DialogueLine(speaker="快递员", line="是谁在说话？"),
                    ],
                    emotional_arc="平静 → 警觉",
                    duration_sec=8.0,
                ),
                Scene(
                    scene_id="SCENE_2",
                    location="废弃服务器机房",
                    time_of_day="深夜",
                    summary="快递员追查记忆去向，撞破真相。",
                    dialogue=None,
                    emotional_arc="警觉 → 震惊",
                    duration_sec=12.0,
                ),
            ],
            emotional_curve=["平稳", "悬疑", "爆发"],
        )
