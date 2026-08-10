# Studio Prompt — 提示词站

## 职责
基于分镜表与视觉圣经，为每镜生成六要素完整视频生成提示词（主体/动作/环境/光照/运镜/情绪），
产出 `prompt_list.json`。

## 归入 Agent
- `agents/prompter.md` — 提示词工程师：六要素提示词 + negative_prompt + 跨镜头一致性

## 输入产物
| 短名 | 契约 | 来源 |
|------|------|------|
| `shoot` | `schemas/shot_list.py::ShotList` | Studio Shoot（03_shoot） |
| `art` | `schemas/visual_bible.py::VisualBible` | Studio Art（02_art） |

## 输出产物
| 文件 | 契约 | 落盘 |
|------|------|------|
| `prompt_list.json` | `schemas/prompt_list.py::PromptList` | `<artifacts>/<project_id>/04_prompt/prompt_list.json` |

## 契约引用
- `schemas/artifact.py` — `ArtifactBase`
- `schemas/prompt_list.py` — `PromptList` / `ShotPrompt`（字段参考 v1 `dual_track.py` 的 `ShotPrompt`）

## 目录映射
manifest `studios` key：**`prompt`** ↔ 磁盘目录 **`04_prompt`**

## 运行
```bash
python studios/studio_prompt/run.py --project demo1
```
> 前置：`03_shoot/shot_list.json` + `02_art/visual_bible.json` 必须存在，否则友好报错。

## 断点续跑 / 人工修改
- 重跑会按 manifest 血缘记录消费的 `shoot` / `art` hash。
- 人工修改 `prompt_list.json` 后：`edited_by="human"`、递增 `version`。
