# sc-materials

SceneCraft 素材卡库（纯标准库）：卡解析 → tag 交集筛选 → 两级排序 → 预算截断。
**不依赖 SceneCraft 主仓**，可独立安装使用；`templates/` 随包分发。

## 安装

```bash
pip install -e packages/sc-materials   # 仓库内可编辑安装
# 或发布后：pip install sc-materials
```

## 最小用法

```python
from sc_materials import pick_materials

# cards_dir 指向你自己的卡片目录（每张卡一个 .md，带 frontmatter）
body = pick_materials("赛博朋克,悬疑", cards_dir="./my-cards", limit=2000)
print(body or "（无匹配卡片）")
```

命令行：`python -m sc_materials.pick --tags 赛博朋克,悬疑 --cards-dir ./my-cards`

`cards_dir` 缺省为包内 `sc_materials/cards/`——发行包只带 `templates/`（卡模板），
实际卡片由使用方提供，因此通常应显式传入。

## 版权闸

- `status` 三态（原创 / 灵感 / 改写），非法或缺失 → 跳过该卡（绝不误标原创）
- 非原创必须标 `source`，缺失 → 跳过
- 注入文本对非原创卡强制带「结构参考勿照搬原文（来源：…）」

## 环境变量

无。
