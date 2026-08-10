# Studio Edit — 剪辑站

## 职责
基于分镜表与剧本，编排剪辑时间线（镜头入出帧 + 转场 + 音频落点），
产出 `editing_blueprint.json`。

## 归入 Agent
- `agents/editor.md` — 剪辑师：TimelineEntry 转场/入出帧、AudioBeat 音频落点

## 输入产物
| 短名 | 契约 | 来源 |
|------|------|------|
| `shoot` | `schemas/shot_list.py::ShotList` | Studio Shoot（03_shoot） |
| `script` | `schemas/script.py::Script` | Studio Story（01_script） |

## 输出产物
| 文件 | 契约 | 落盘 |
|------|------|------|
| `editing_blueprint.json` | `schemas/editing_blueprint.py::EditingBlueprint` | `<artifacts>/<project_id>/05_edit/editing_blueprint.json` |

## 契约引用
- `schemas/artifact.py` — `ArtifactBase`
- `schemas/editing_blueprint.py` — `EditingBlueprint` / `TimelineEntry` / `AudioBeat`
  （字段参考 v1 `dual_track.py` 的 `EditingTimelineBlueprint`）

## 目录映射
manifest `studios` key：**`edit`** ↔ 磁盘目录 **`05_edit`**

## 运行
```bash
python studios/studio_edit/run.py --project demo1
```
> 前置：`03_shoot/shot_list.json` + `01_script/script.json` 必须存在，否则友好报错。

## 断点续跑 / 人工修改
- 重跑会按 manifest 血缘记录消费的 `shoot` / `script` hash。
- 人工修改 `editing_blueprint.json` 后：`edited_by="human"`、递增 `version`。
