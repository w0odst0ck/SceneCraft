# test-results/ — SceneCraft 链路测试台账

每次链路测试的**结论与证据索引**。产物真相源在 `artifacts/<project_id>/`（各站 run.py 落盘），
本目录只放矩阵与指向证据的链接，不复制产物。更新方式：跑完一轮测试 → 改本文件对应行。

## 测试矩阵（2026-09-08）

| 链路 | 状态 | 证据（artifacts/） | 后端 | 成本 | 备注 |
|---|---|---|---|---|---|
| 文本七站（script→edit） | ✅ 单站验证 | `test-coffee-14b3`（script） | 本地 14b（test 档） | $0 | 素材卡注入成功；全链待 S5 验收 |
| 视频 render（→Wan/LTX） | ⏳ 未测 | — | — | — | benchmark 后接 adapter（plan/链路修正与两环境方案.md §3） |
| QC | ⏳ 未测 | — | — | — | 全链跑通后追加 |

## 两环境（plan/链路修正与两环境方案.md §2）

- `SCENE_ENV=test` → 本地 ollama（¥0，开发/链路验证）｜`SCENE_ENV=prod` → DeepSeek（成品）
- 切换：`scripts/scene-env.sh test|prod`；run_pipeline 启动打印当前环境

## 历史轮次

- 2026-09-07：test-coffee-0907/0907b —— 本地 9b 剧本格式不稳
- 2026-09-08：test-coffee-14b3 —— 本地 14b 剧本通过（素材注入 + JSON 契约合规）→ 文本链路单站验证 ✅
- 2026-09-08 晚：误插 SDXL 静态图环节（非主链）→ 2026-09-08 清理撤回，链路语义恢复「文本七站 → 视频」

## 约定

- 本目录 README 入仓（gitignore：子目录产物快照不入仓）
- 代码/配置改动走 collab-flow workitem；跑测结果直接更新本矩阵
