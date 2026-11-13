"""ArtifactBase — 跨工作室产物血缘基类

所有中间产物（Script / VisualBible / ShotList / PromptList / EditingBlueprint）
都继承本类，携带血缘字段：
- upstream_hash: 记录每个上游产物的内容 hash，支撑断点续跑 / 单站重跑追踪
- edited_by:     "human" 表示人工修改过，AI 重跑时必须保护，防止覆盖人工修改
- version:       产物版本号（人工修改后递增）
- output_hash:   本产物内容 hash，由 compute_hash() 计算后回填
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field


def content_hash(raw: Any) -> str:
    """对任意 JSON 可序列化对象计算内容 hash（SHA-256 前 12 位十六进制）。

    序列化使用 sort_keys + 紧凑分隔符，保证同内容必同 hash，便于人读与血缘比对。
    """
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


class ArtifactBase(BaseModel):
    """所有工作室产物的血缘基类。"""

    upstream_hash: dict[str, str] = Field(
        default_factory=dict,
        description="每个上游产物的内容 hash，键为上游产物短名，如 {\"script\": \"abc123\"}",
    )
    edited_by: Literal["ai", "human"] = Field(
        default="ai", description="人工修改标记；human 表示人工改过，AI 重跑不得覆盖"
    )
    version: int = Field(default=1, ge=0, description="产物版本号")
    output_hash: str | None = Field(
        default=None, description="本产物内容 hash（由 compute_hash() 计算后回填）"
    )

    def compute_hash(self) -> str:
        """基于产物内容计算内容 hash。

        排除 output_hash 自身（它是派生的），保证「同内容必同 hash」，
        也避免写盘回填 hash 后再次计算发生漂移。
        """
        payload = self.model_dump(exclude={"output_hash"}, mode="json")
        return content_hash(payload)
