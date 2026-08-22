# story-materials — SceneCraft 剧本素材库

为 `studio_story` 的 writer 提供**结构化素材卡**：按 tag 把 5–10 张卡注入 writer 的 prompt（MissionPlan JSON 之后、输出契约之前），缓解「剧本套路化、细节空」——素材是参考锚点，不是照抄底稿。

## 目录结构

```
story-materials/
  README.md          # 本文件（使用说明 + 版权红线，先用它）
  templates/         # 6 类模板：复制→填写→存 cards/
  cards/             # 一张卡一文件（<id>.md，如 2026-08-22-001.md）
  scripts/
    pick_materials.py  # 纯 stdlib：筛选→排序→拼注入文本（无 PyYAML）
```

## 怎么积累素材

1. 你积累一段素材（一句话、一个生活观察、一段情节构思都行）。
2. 从 `templates/` 选最贴近的一类（setting 设定 / character 人物 / beat 桥段 / theme 主题 / line 金句 / detail 细节），复制到 `cards/`，改名为 `<id>.md`（`YYYY-MM-DD-NNN`，全库唯一）。
3. 按模板填齐字段：frontmatter（id/type/tags/status/source/priority）+ 三个正文节（核心设定/可复用点/版权备注）。
4. `tags` 至少 1 个，**建议打 2–4 个语义近邻 tag**（如「赛博朋克, 悬疑, 雨夜」），因为匹配是精确交集，同义不同词会漏命中（如「赛博」≠「赛博朋克」）。

## 怎么用

```bash
# 剧本站注入素材（命中则注入，未命中不影响流程）
python studios/studio_story/run.py --project demo --concept "雨夜便利店的神秘顾客" \
    --material-tags 赛博朋克,悬疑 --demo

# 单独预览会注入什么（不跑 agent）
python story-materials/scripts/pick_materials.py --tags 赛博朋克,悬疑
```

- `--material-tags` 逗号分隔（全角逗号也认），**不传则行为与旧版完全一致**。
- 注入位置：MissionPlan JSON 之后、Script 契约示例之前；注入段开头声明 **「与 concept 冲突时以 concept 为准」**——你的概念永远是第一优先级。
- 预算：总输出 ≤2000 字符；预算不足时**丢整卡**（优先牺牲 backup 尾部），绝不半切字段；每类（type）最多 2 张。

## 版权红线（必读）

卡片 `status` 三态，**决定这张卡能不能直接注入**：

| status | 含义 | 能否直接用 |
|---|---|---|
| `原创` | 你自己写的内容 | ✅ 直接可用 |
| `灵感` | 受他人作品启发，**只借鉴结构**，表达全部自写 | ⚠️ 注入时透传「结构参考勿照搬原文」+ `source` |
| `改写` | 在他人结构基础上改写表达 | ⚠️ 同上，且必须在「版权备注」写清改了什么 |

强制规则（机器强制执行 + 人工自觉）：
- **非原创必标 `source`**（作品名/出处），并在「版权备注」写清：借鉴了什么结构、改写了什么表达。
- **非法/缺失 status 的卡会被直接跳过**（fail-closed）：绝不默认当「原创」注入——这是设计红线。
- 注入渲染时，非原创卡强制带出 `⚠ 结构参考勿照搬原文（来源：…）`，拿到的是结构启发，不是原文复制。
- 金句卡（line）尤其小心：非原创金句不要整句照搬进对白，改造成自己的表达。

## 卡片规范速查

frontmatter 字段（`templates/` 里每个都有注释引导）：

| 字段 | 必填 | 取值 |
|---|---|---|
| `id` | ✅ | 日期-序号（`2026-08-22-001`），全库唯一 |
| `type` | ✅ | 六选一：setting / character / beat / theme / line / detail |
| `tags` | ✅ | 至少 1 个，`[a, b]` 或 `a, b` 写法均可 |
| `status` | ✅ | 三选一：原创 / 灵感 / 改写 |
| `source` | 非原创必填 | 来源标注，仅标注不照搬 |
| `priority` | 否 | core 核心 / backup 备用（缺失视为 backup） |

正文三节：`# 标题`（缺了会用文件名兜底）、`## 核心设定`、`## 可复用点`（必填节，缺了整卡被跳过）、`## 版权备注`。

## 数据与故障说明

- 卡片数据异常（坏 frontmatter、非法 type/status、缺可复用点、非 UTF-8）→ **只跳过那一张** + stderr 警告，其余卡正常，全库流程不崩。
- 无匹配 / 空库 / 空 tags → 返回空串，exit 0，不报错；`run.py` 不注入任何素材段。
- 显式传了 `--material-tags` 但 `pick_materials.py` 缺失 → 报错退出（fail-closed，不静默丢素材）。
- 本库**零依赖**（纯 Python 标准库），`requirements.txt` 不需要任何改动。
