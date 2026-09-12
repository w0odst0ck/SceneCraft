# test-results/ — SceneCraft 链路测试台账

每次链路测试的**结论与证据索引**。产物真相源在 `artifacts/<project_id>/`（各站 run.py 落盘），
本目录只放矩阵与指向证据的链接，不复制产物。更新方式：跑完一轮测试 → 改本文件对应行。

## 测试矩阵（2026-09-12）

| 链路 | 状态 | 证据（artifacts/） | 后端 | 成本 | 备注 |
|---|---|---|---|---|---|
| 文本七站（script→edit） | ✅ 全链通过 | `t1-coffee-envtest`（6 站产物齐） | 本地 14b-ctx2k（test 档） | $0 | 分批改造后 14 镜/14 条 timeline 完整 |
| 视频 render（LTX 2B） | ✅ **全链出片** | `t1-coffee-envtest/06_render/*.webm` | ComfyUI + LTX 2B（本地） | ¥0 | **14/14 镜**；单镜 ~55s；峰值显存 11940 MiB；总片长 27.4s |
| QC | ⏳ 待跑 | — | — | — | 全链（concept 起）--qc 时追加 |
| 画质（成品档） | ⚠️ 本地不达标 | `plan/s3-spike-samples/` | LTX 2B / 13B fp8 | ¥0 | 语义偏模糊：测试可用、成品不行 → 成品走 minimax API/云 GPU（roadmap 阶段二/三） |

## 两环境（plan/链路修正与两环境方案.md §2）

- `SCENE_ENV=test` → 本地 ollama（¥0，开发/链路验证）｜`SCENE_ENV=prod` → DeepSeek（成品）
- 切换：`scripts/scene-env.sh test|prod`；run_pipeline 启动打印当前环境

## 历史轮次

- 2026-09-07：test-coffee-0907/0907b —— 本地 9b 剧本格式不稳
- 2026-09-08：test-coffee-14b3 —— 本地 14b 剧本通过（素材注入 + JSON 契约合规）→ 文本链路单站验证 ✅
- 2026-09-08 晚：误插 SDXL 静态图环节（非主链）→ 2026-09-08 清理撤回，链路语义恢复「文本七站 → 视频」
- 2026-09-09~11：两环境正式化（SCENE_ENV）· 分批生成改造（shoot/prompt/edit + 批内重试）→ 文本全链 14 镜/14 条通过
- 2026-09-11 夜：LTX 2B spike 通过（12GB 卡可跑）；LTX 13B fp8 亦可跑但慢 6×
- 2026-09-12：**render 站接真实渲染**（commit 867ab80）→ 全链 14/14 镜出片 ✅

## 约定

- 本目录 README 入仓（gitignore：子目录产物快照不入仓）
- 代码/配置改动走 collab-flow workitem；跑测结果直接更新本矩阵
