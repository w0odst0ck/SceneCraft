"""薄转发层（M0 抽包）：实现已迁至 packages/sc-materials/src/sc_materials/pick.py。

用 sys.modules 别名 + 覆盖 DEFAULT_CARDS_DIR：
- monkeypatch/模块状态与实现同源；
- 默认卡片目录仍是 story-materials/cards（与搬迁前完全一致）。
"""
import sys
from pathlib import Path

from sc_materials import pick as _impl

# 主仓默认卡片目录保持原语义：story-materials/cards
_impl.DEFAULT_CARDS_DIR = Path(__file__).resolve().parents[1] / "cards"

sys.modules[__name__] = _impl

if __name__ == "__main__":
    sys.exit(_impl.main())
