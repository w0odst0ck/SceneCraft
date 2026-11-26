# ComfyUI-SceneCraft

**给 ComfyUI 用的 AI 短剧工具节点**：素材库（带版权闸）+ 卡片检查器。

> 解决的问题不是「再做一个生成节点」——ComfyUI 已有 6000+ 节点包。
> 这里做的是**生成之前**的两件事：**素材怎么来**、**长文本怎么不截断**。

---

## 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/<your-name>/ComfyUI-SceneCraft.git
# 重启 ComfyUI
```

无需 `pip install`。节点是**零依赖**的（纯标准库）。

---

## 节点

### 🗂 SC Material Library（素材库）

按 tags 从素材卡库筛选卡片，输出可直接拼进 prompt 的文本。

| 输入 | 说明 |
|---|---|
| `tags` | 逗号分隔，精确交集匹配（如 `治愈,善意`） |
| `cards_dir` | 卡片目录（默认 `./cards`） |
| `limit_chars` | 字符预算（默认 2000，预算不足丢整卡不半切） |
| `per_type_max` | 每类最多几张（默认 2） |

| 输出 | 说明 |
|---|---|
| `material_text` | 可直接连到 CLIPTextEncode 的注入文本 |
| `summary` | 命中统计（调试用） |

**版权闸（本节点的核心设计）**：
素材卡有 `status` 三态 —— `原创` / `灵感` / `改写`。
- 非原创卡**强制带出来源 + 「⚠ 结构参考勿照搬原文」**
- `status` 缺失或非法的卡**直接跳过**（fail-closed，绝不默认当原创）

### 🔍 SC Card Inspector（卡片检查）

查看卡片库统计：有效卡片数、类型分布、版权状态、全部可用 tags、非法卡警告。

---

## 素材卡格式

在 `cards/` 放 `*.md`，frontmatter + 三个正文节：

```
---
id: <唯一ID>          type: beat|character|theme|line|detail|setting
tags: [治愈, 善意]     status: 原创|灵感|改写   ← 缺失/非法则跳过
source: <非原创必填>   priority: core|backup
---
# 标题

## 核心设定
...
## 可复用点          ← 必填，缺了整卡跳过
...
```


| 字段 | 必填 | 取值 |
|---|---|---|
| `type` | ✅ | `setting` / `character` / `beat` / `theme` / `line` / `detail` |
| `tags` | ✅ | 至少 1 个；支持 `[a, b]` 或 `a, b` 或全角逗号 |
| `status` | ✅ | `原创` / `灵感` / `改写`（缺失→跳过） |
| `source` | 非原创必填 | 来源标注（仅标注，不照搬） |
| `priority` | — | `core` / `backup`（缺失视为 backup） |

正文必须含 `## 可复用点`（缺了整卡跳过）。

---

## 许可

MIT
