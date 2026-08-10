# Studio Story — 剧本站

## 职责
接收用户创意概念（字符串，经 `--concept` 传入），产出完整剧本 `script.json`。
本工作室**无上游产物输入**，是管线的第一站。

## 归入 Agent
- `agents/producer.md` — 总制片人：拆解概念为创作目标（类型/时长/镜头数/情绪基调）
- `agents/writer.md` — 编剧：生成完整剧本

## 输入产物
| 短名 | 契约 | 来源 |
|------|------|------|
| （无） | — | 用户概念字符串（CLI `--concept`） |

## 输出产物
| 文件 | 契约 | 落盘 |
|------|------|------|
| `script.json` | `schemas/script.py::Script` | `<artifacts>/<project_id>/01_script/script.json` |

## 契约引用
- `schemas/artifact.py` — `ArtifactBase`（血缘字段：`upstream_hash` / `edited_by` / `version` / `output_hash`）
- `schemas/script.py` — `Script` / `Scene`

## 目录映射
manifest `studios` key：**`script`** ↔ 磁盘目录 **`01_script`**

## 运行
```bash
python studios/studio_story/run.py --project demo1 --concept "赛博快递员发现义体在收集记忆"
```

## 断点续跑 / 人工修改
- 本站无上游产物，重跑只需再次执行 run.py（新项目首次运行自动创建 manifest）。
- 人工修改 `script.json` 后须把 `edited_by` 置为 `"human"` 并递增 `version`，
  下游工作室（art/shoot/edit/qc）重跑时会校验血缘。
