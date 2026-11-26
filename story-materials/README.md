# story-materials

**剧本素材库**：为剧本站的 writer 提供结构化素材卡，按 tag 注入 prompt，缓解「剧本套路化、细节空」。

## 格式

卡片放在 `cards/`，一个文件一张卡：

```
---
id: 2026-11-26-001
type: beat              # setting|character|beat|theme|line|detail
tags: [治愈, 善意]       # 至少 1 个
status: 改写            # 原创|灵感|改写（缺失/非法 → 跳过）
source: "出处"          # 非原创必填
priority: core          # core|backup
---
# 标题

## 核心设定
...

## 可复用点             ← 必填，缺了整卡跳过
...
```

## 用法

```bash
# 预览会注入什么
python story-materials/scripts/pick_materials.py --tags 治愈,善意

# 跑剧本站时注入
python studios/studio_story/run.py --project demo --concept "..." --material-tags 治愈,善意
```

## 版权三态（fail-closed）

| status | 含义 |
|---|---|
| `原创` | 自己写的，可直接用 |
| `灵感` | 受启发，只借鉴结构，表达自写 |
| `改写` | 结构基础上改写表达 |

非原创卡注入时强制带出「⚠ 结构参考勿照搬原文（来源：…）」。
`status` 缺失或非法的卡**直接跳过**——绝不默认当原创。

实现见 `packages/sc-materials/`。
