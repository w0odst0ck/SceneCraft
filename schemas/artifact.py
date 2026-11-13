"""薄转发层（M0 抽包）：实现已迁至 packages/sc-contracts/src/sc_contracts/artifact.py。

保留本文件只为兼容旧 import 路径（`from schemas.artifact import ArtifactBase`）。
"""
from sc_contracts.artifact import ArtifactBase, content_hash

__all__ = ["ArtifactBase", "content_hash"]
