"""Critic: 质检报告"""

from typing import Optional
from pydantic import BaseModel, Field


class CriticFinding(BaseModel):
    severity: str = Field(..., pattern=r"^(critical|suggestion|nitpick)$")
    target_agent: str
    target_shot: Optional[str] = None
    issue: str
    suggested_fix: str


class CriticReport(BaseModel):
    stage: str = Field(..., description="初审/终审")
    passed: bool
    total_score: float = Field(..., ge=0, le=100)
    consistency_score: float = Field(default=0, ge=0, le=100)
    feasibility_score: float = Field(default=0, ge=0, le=100)
    findings: list[CriticFinding]
    summary: str
