# Studio Render — 日志目录

本目录存放渲染站每次运行的日志（Phase B 起启用）：
- `run-YYYYMMDD-HHMMSS.log` — 每次运行的工作日志（含 bridge 调用记录）
- `decision-log.md` — 重要决策记录（含人工修改记录）

约定：
- 日志只追加、不覆盖。
- 人工修改产物时，须在 `decision-log.md` 记录，并把产物 `edited_by` 置为 `"human"`。
