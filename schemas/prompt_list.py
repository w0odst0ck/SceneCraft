"""PromptList — 提示词列表产物（Studio Prompt 输出）

参考 v1 ai-short-drama/schemas/dual_track.py 的 ShotPrompt 设计：
shot_id + 六要素完整提示词（主体 / 动作 / 环境 / 光照 / 运镜 / 情绪）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.artifact import ArtifactBase


class ShotPrompt(BaseModel):
    """单镜头的视频生成提示词。"""

    shot_id: str = Field(..., description="对应镜头 ID，须与 shot_list 一致")
    prompt: str = Field(..., description="六要素完整提示词（主体/动作/环境/光照/运镜/情绪）")
    negative_prompt: str = Field(default="", description="负面提示词")
    model: str = Field(default="Kling 2.0", description="视频生成模型")
    aspect_ratio: str = Field(default="16:9", description="画幅比")


class PromptList(ArtifactBase):
    """提示词列表：全局模型/画幅 + 按 shot_id 索引的提示词。"""

    model: str = Field(..., description="全局默认视频生成模型")
    aspect_ratio: str = Field(..., description="全局默认画幅比")
    prompts: dict[str, ShotPrompt] = Field(..., description="提示词映射，key = shot_id")

    @classmethod
    def demo(cls) -> "PromptList":
        """demo 实例：字段齐全、校验通过。"""
        return cls(
            model="Kling 2.0",
            aspect_ratio="16:9",
            prompts={
                "SHOT_1": ShotPrompt(
                    shot_id="SHOT_1",
                    prompt="雨夜霓虹城区，年轻快递员在派件，义体右臂 LED 闪烁，"
                    "青蓝主光品红轮廓光，中景略仰机位，缓慢推近，情绪警觉。",
                    negative_prompt="变形、多余肢体、低画质",
                    model="Kling 2.0",
                    aspect_ratio="16:9",
                ),
            },
        )
