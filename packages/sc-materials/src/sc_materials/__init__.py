"""sc_materials — SceneCraft 素材卡库（纯 stdlib，带版权闸）

M0 抽包：由 SceneCraft 仓库 `story-materials/scripts/pick_materials.py` 原样搬迁为
`sc_materials.pick`；卡解析/筛选/排序/预算截断逻辑未改动。`templates/` 随包分发。

最小用法：
    from sc_materials import pick_materials
    body = pick_materials("赛博朋克,悬疑", cards_dir="./story-materials/cards")
"""
from sc_materials.pick import (
    DEFAULT_CARDS_DIR,
    HEADER,
    LIMIT,
    PER_TYPE_CAP,
    PRIORITIES,
    SIX_TYPES,
    STATUSES,
    Card,
    MalformedCard,
    load_cards,
    main,
    parse_card,
    pick_materials,
    render,
    render_card,
    select_cards,
)

__all__ = [
    "pick_materials",
    "load_cards",
    "parse_card",
    "select_cards",
    "render",
    "render_card",
    "Card",
    "MalformedCard",
    "DEFAULT_CARDS_DIR",
    "HEADER",
    "LIMIT",
    "PER_TYPE_CAP",
    "SIX_TYPES",
    "STATUSES",
    "PRIORITIES",
    "main",
]
