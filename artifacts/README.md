# artifacts/ — 产物仓库（JSON 为准）

每个项目的所有中间产物 + 台账都落在这里，是 v2 多工作室架构的「显式中间层」，
支撑断点续跑 / 单站重跑 / 人工修改产物。

## 目录结构

```
artifacts/
  <project_id>/
    manifest.json              # 项目台账：7 个工作室状态 + hash 血缘（唯一事实源）
    01_script/script.json      # Studio Story 输出
    02_art/visual_bible.json   # Studio Art 输出
    03_shoot/shot_list.json    # Studio Shoot 输出
    04_prompt/prompt_list.json # Studio Prompt 输出
    05_edit/editing_blueprint.json  # Studio Edit 输出
    06_render/…                # 视频产物（Phase B 接入 bridge 后生成）
    07_qc/qc_report.json       # Studio QC 输出
```

实际项目目录由各工作室的 `run.py` 生成，本仓库仅跟踪 README 与目录占位。

## 双格式原则

- **JSON 为准**：一切自动化流程（断点续跑 / 单站重跑 / 人工修改）只认 JSON 产物，
  字段与血缘定义见顶层 `schemas/`。
- **MD 人读只读**：Phase B 可为人工审阅生成 Markdown 视图，但 MD 一律**只读**；
  任何人 / Agent 修改产物都必须改 JSON，再由脚本重新生成 MD，禁止直接改 MD。

## 约定

- manifest 的 `studios` key 用工作室短名：`script/art/shoot/prompt/edit/render/qc`，
  对应磁盘目录 `01_script … 07_qc`（映射见各 `studios/*/SKILL.md`）。
- 每个产物 JSON 自带血缘字段（`upstream_hash` / `edited_by` / `version` / `output_hash`），
  定义见 `schemas/artifact.py`；`edited_by: "human"` 表示人工修改过，AI 重跑不得覆盖。
- 缺输入跑某工作室时，`run.py` 会友好报错并提示先运行上游工作室。
