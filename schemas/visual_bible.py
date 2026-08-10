"""VisualBible — 视觉圣经产物（Studio Art 输出）

v2 新增契约：定义整剧视觉语言——色彩基调 / 材质 / 光照 / 角色造型 / 美术备注。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.artifact import ArtifactBase


class ColorPalette(BaseModel):
    """色彩基调：主色 / 辅色 / 强调色 + 情绪描述。"""

    primary: str = Field(..., description="主色，如 #1a1a2e（暗夜蓝）")
    secondary: str = Field(..., description="辅色")
    accent: str = Field(..., description="强调色")
    mood: str = Field(..., description="色彩基调传达的情绪，如 冷峻疏离")


class CharacterDesign(BaseModel):
    """单个角色的造型设计。"""

    character: str = Field(..., description="角色名，须与 script 中保持一致")
    appearance: str = Field(..., description="外观描述")
    costume: str = Field(..., description="服装造型")
    color_key: str = Field(..., description="角色专属色")


class VisualBible(ArtifactBase):
    """整剧视觉圣经。"""

    color_palette: ColorPalette = Field(..., description="色彩基调")
    material_style: str = Field(..., description="材质风格，如 亚光金属 + 霓虹玻璃")
    lighting_style: str = Field(..., description="光照风格，如 高反差霓虹夜景")
    character_designs: list[CharacterDesign] = Field(..., description="角色造型列表")
    art_notes: list[str] = Field(default_factory=list, description="美术备注（场景概念关键词等）")

    @classmethod
    def demo(cls) -> "VisualBible":
        """demo 实例：字段齐全、校验通过。"""
        return cls(
            color_palette=ColorPalette(
                primary="#1a1a2e",
                secondary="#16213e",
                accent="#e94560",
                mood="冷峻疏离的赛博夜城",
            ),
            material_style="亚光金属 + 霓虹玻璃 + 湿润沥青",
            lighting_style="高反差霓虹夜景，青蓝主光 + 品红轮廓光",
            character_designs=[
                CharacterDesign(
                    character="快递员",
                    appearance="年轻男性，义体右臂带 LED 灯带",
                    costume="防水冲锋衣 + 反光背心",
                    color_key="#00d2ff",
                ),
            ],
            art_notes=["霓虹城区", "废弃机房", "雨夜反光"],
        )
