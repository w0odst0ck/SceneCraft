"""QcReport — 质检报告产物（Studio QC 输出）

v2 横切站契约：critic 检查任意站产物后输出质检报告。
- stage:       被检工作室短名（如 script / shot_list 所属站）
- total_score: 0-100 综合评分
- findings:    发现列表（critical / suggestion / nitpick 三级）
- passed:      由 total_score >= 60 推导（computed_field，随评分自动一致）
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

from schemas.artifact import ArtifactBase

# 评分及格线：total_score >= 60 视为通过
PASS_THRESHOLD = 60


class QcFinding(BaseModel):
    """单条质检发现。"""

    severity: Literal["critical", "suggestion", "nitpick"] = Field(
        ..., description="严重等级：critical 必须修复 / suggestion 建议修复 / nitpick 锦上添花"
    )
    location: str = Field(..., description="问题位置，如 SCENE_1 / SHOT_3 / 全局")
    message: str = Field(..., description="问题描述与修改建议")


class QcReport(ArtifactBase):
    """质检报告：被检站 + 评分 + 发现列表。"""

    stage: str = Field(..., description="被检工作室短名（如 script / shoot）")
    total_score: float = Field(..., ge=0, le=100, description="综合评分（0-100）")
    findings: list[QcFinding] = Field(default_factory=list, description="质检发现列表")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        """是否通过：total_score >= 60（由评分自动推导，避免与分数不一致）。"""
        return self.total_score >= PASS_THRESHOLD

    @classmethod
    def demo(cls) -> "QcReport":
        """demo 实例：字段齐全、校验通过。"""
        return cls(
            stage="script",
            total_score=85.0,
            findings=[
                QcFinding(
                    severity="suggestion",
                    location="SCENE_1",
                    message="开场可以更早给出冲突钩子，建议增加一句对白。",
                ),
            ],
        )
