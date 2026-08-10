"""ShotList — 分镜表产物（Studio Shoot 输出）

参考 v1 ai-short-drama/schemas/shot_list.py 的 ShotParameterCard 字段设计
（shot_id / scene_id / duration / subject / action / emotion / environment /
 lighting / camera_angle / camera_movement / focal_length / narrative_purpose）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.artifact import ArtifactBase


class Shot(BaseModel):
    """单镜头参数卡。"""

    shot_id: str = Field(..., pattern=r"^SHOT_\d+$", description="镜头 ID，如 SHOT_1")
    scene_id: str = Field(..., pattern=r"^SCENE_\d+$", description="所属场次 ID")
    duration: float = Field(..., gt=0, description="镜头时长（秒）")
    subject: str = Field(..., description="主体描述")
    action: str = Field(..., description="动作描述")
    emotion: str = Field(..., description="情绪状态")
    environment: str = Field(..., description="环境描述")
    lighting: str = Field(..., description="光影方案")
    camera_angle: str = Field(..., description="机位角度")
    camera_movement: str = Field(..., description="运镜轨迹")
    focal_length: str = Field(default="50mm", description="焦段")
    narrative_purpose: str = Field(..., description="本镜头叙事目的")


class ShotList(ArtifactBase):
    """分镜表：目标镜头数 + 镜头列表。"""

    target_shots: int = Field(..., gt=0, description="计划镜头总数")
    shots: list[Shot] = Field(..., description="镜头列表")

    @classmethod
    def demo(cls) -> "ShotList":
        """demo 实例：字段齐全、校验通过。"""
        return cls(
            target_shots=1,
            shots=[
                Shot(
                    shot_id="SHOT_1",
                    scene_id="SCENE_1",
                    duration=3.0,
                    subject="快递员",
                    action="在雨夜派件，义体右臂突然闪烁",
                    emotion="警觉",
                    environment="霓虹城区，雨夜",
                    lighting="青蓝主光 + 品红轮廓光",
                    camera_angle="中景，略仰",
                    camera_movement="缓慢推近",
                    focal_length="35mm",
                    narrative_purpose="交代主角与义体异常",
                ),
            ],
        )
