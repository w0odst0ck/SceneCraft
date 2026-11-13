# sc-materials

SceneCraft 素材卡库（纯标准库）：卡解析 → tag 交集筛选 → 两级排序 → 预算截断。M0 抽包：
由主仓 `story-materials/scripts/pick_materials.py` 原样搬迁，逻辑未改动；`templates/` 随包分发。

## 版权闸

- `status` 三态（原创 / 灵感 / 改写），非法或缺失 → 跳过该卡（绝不误标原创）
- 非原创必须标 `source`，缺失 → 跳过
- 注入文本对非原创卡强制带「结构参考勿照搬原文（来源：…）」

## 最小用法

```python
from sc_materials import pick_materials

body = pick_materials("赛博朋克,悬疑", cards_dir="./story-materials/cards", limit=2000)
```

命令行：`python -m sc_materials.pick --tags 赛博朋克,悬疑 --cards-dir <dir>`
