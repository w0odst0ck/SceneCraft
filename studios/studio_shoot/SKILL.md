# Studio Shoot — 分镜站

## 职责
基于剧本与视觉圣经，拆解镜头序列，为每镜标注机位/运镜/焦段/光影/表演，
产出分镜表 `shot_list.json`。

## 归入 Agent
- `agents/director.md` — 导演：镜头序列编排，覆盖全部剧情节点
- `agents/cinematographer.md` — 摄影：机位角度 / 运镜轨迹 / 焦段 / 光影方案
- `agents/actor.md` — 演员：动作与情绪表演细节

## 输入产物
| 短名 | 契约 | 来源 |
|------|------|------|
| `script` | `schemas/script.py::Script` | Studio Story（01_script） |
| `art` | `schemas/visual_bible.py::VisualBible` | Studio Art（02_art） |

## 输出产物
| 文件 | 契约 | 落盘 |
|------|------|------|
| `shot_list.json` | `schemas/shot_list.py::ShotList` | `<artifacts>/<project_id>/03_shoot/shot_list.json` |

## 契约引用
- `schemas/artifact.py` — `ArtifactBase`
- `schemas/shot_list.py` — `ShotList` / `Shot`（字段参考 v1 `ShotParameterCard`）

## 目录映射
manifest `studios` key：**`shoot`** ↔ 磁盘目录 **`03_shoot`**

## 运行
```bash
python studios/studio_shoot/run.py --project demo1
```
> 前置：`01_script/script.json` + `02_art/visual_bible.json` 必须存在，否则友好报错。

## 断点续跑 / 人工修改
- 重跑会按 manifest 血缘记录消费的 `script` / `art` hash。
- 人工修改 `shot_list.json` 后：`edited_by="human"`、递增 `version`。
