# Studio QC — 质检站

## 职责
检查任意站产物，按严重等级（critical / suggestion / nitpick）输出问题，
给出质检结论（pass / revise），产出 `qc_report.json`。
**Phase A 仅占位**：报告骨架标注 `TODO_PHASE_B`，真实质检逻辑 Phase B 填充。

## 归入 Agent
- `agents/critic.md` — 批评家：独立质检，不创作、不修改任何文件

## 输入产物
| 短名 | 契约 | 来源 |
|------|------|------|
| 任意站产物（`--input-stage` 指定，默认 `script`） | 不绑定契约（`common.load_raw`） | 对应工作室目录 |

支持的目标短名：`script / art / shoot / prompt / edit / render / qc`

## 输出产物
| 文件 | 契约 | 落盘 |
|------|------|------|
| `qc_report.json`（占位） | `run.py::QcReport` | `<artifacts>/<project_id>/07_qc/qc_report.json` |

## 契约引用
- `schemas/artifact.py` — `ArtifactBase`
- `studios/common.py` — `load_raw`（任意站产物读取）/ `DEFAULT_FILES`（短名→文件名映射）

## 目录映射
manifest `studios` key：**`qc`** ↔ 磁盘目录 **`07_qc`**

## 运行
```bash
# 检查剧本
python studios/studio_qc/run.py --project demo1 --input-stage script
# 检查分镜表
python studios/studio_qc/run.py --project demo1 --input-stage shoot
```
> 前置：目标站产物必须存在，否则友好报错提示先运行对应工作室。

## 断点续跑 / 人工修改
- 重跑会按 manifest 血缘记录本次检查目标产物的 hash。
- `verdict=revise` 时（Phase B 起）应退回对应工作室重跑，仅退回单一工作室，不全局重跑。
