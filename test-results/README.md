# test-results/ — SceneCraft 测试产出总目录（台账 + 产物）

**所有测试产出统一放这里**（2026-09-13 定）。`artifacts/` 只留给正式产物；
测试跑法一律带 `--artifacts-dir test-results/`，产物即落在 `test-results/<project_id>/`。

## 目录结构

```
test-results/
  README.md                    # 本文件（测试矩阵 + 约定；唯一入仓文件）
  <project_id>/                # 单个测试项目（各站 run.py 生成）
    manifest.json              # 项目台账：工作室状态 + hash 血缘
    01_script … 05_edit/       # 文本五站产物（JSON 为准）
    06_render/*.webm           # 视频产物（LTX 2B via ComfyUI 本地渲染）
  s3-spike-samples/            # 视频模型 spike 样片（LTX 2B / 13B fp8）
```

## 怎么跑（测试）

```bash
cd projects/SceneCraft
source scripts/scene-env.sh test                       # 本地 ollama（¥0）
python studios/run_pipeline.py --project <id> --concept "..." \
       --artifacts-dir test-results/ [--material-tags a,b] [--render] [--render-limit N] [--qc]
```

- 默认（不带 `--render`）：只出 render_plan 任务卡（不渲染）
- `--render`：真实渲染出片（LTX 2B，单镜 ~50s，峰值显存 ~11GB，**须独占 GPU**）

## 测试矩阵（2026-09-12）

| 链路 | 状态 | 证据（test-results/） | 后端 | 成本 | 备注 |
|---|---|---|---|---|---|
| 文本七站（script→edit） | ✅ 全链通过 | `t1-coffee-envtest/`（6 站产物齐） | 本地 14b-ctx2k（test 档） | $0 | 分批改造后 14 镜/14 条 timeline 完整 |
| 视频 render（LTX 2B） | ✅ **全链出片** | `t1-coffee-envtest/06_render/*.webm` | ComfyUI + LTX 2B（本地） | ¥0 | **14/14 镜**；单镜 ~47s；峰值显存 11791 MiB；总片长 27.4s |
| QC | ⏳ 待跑 | — | — | — | `--qc` 全链时追加 |
| 画质（成品档） | ⚠️ 本地不达标 | `s3-spike-samples/` | LTX 2B / 13B fp8 | ¥0 | 语义偏模糊：测试可用、成品不行 → 成品走 minimax API/云 GPU（roadmap 阶段二/三） |

## 两环境（plan/链路修正与两环境方案.md §2）

- `SCENE_ENV=test` → 本地 ollama（¥0，开发/链路验证）｜`SCENE_ENV=prod` → DeepSeek（成品）
- 切换：`scripts/scene-env.sh test|prod`；run_pipeline 启动打印当前环境

## 历史轮次

- 2026-09-07：test-coffee-0907/0907b —— 本地 9b 剧本格式不稳
- 2026-09-08：test-coffee-14b3 —— 本地 14b 剧本通过（素材注入 + JSON 契约合规）→ 文本链路单站验证 ✅
- 2026-09-08 晚：误插 SDXL 静态图环节（非主链）→ 当日清理撤回，链路语义恢复「文本七站 → 视频」
- 2026-09-09~11：两环境正式化（SCENE_ENV）· 分批生成改造（shoot/prompt/edit + 批内重试）→ 文本全链 14 镜/14 条通过
- 2026-09-11 夜：LTX 2B spike 通过（12GB 卡可跑）；LTX 13B fp8 亦可跑但慢 6×
- 2026-09-12：**render 站接真实渲染**（commit 867ab80）→ 全链 14/14 镜出片 ✅
- 2026-09-13：**测试产出统一迁入本目录**（原 `artifacts/*` 20 个项目 + `plan/s3-spike-samples` 迁入）

## 约定

- 本目录 README 入仓；子目录产物快照 gitignore（`.gitignore`: `test-results/*/`）
- 代码/配置改动走 collab-flow workitem；跑测结果直接更新本矩阵
- 产出路径在产物内为**相对 artifacts 根**（如 `t1-coffee-envtest/06_render/SHOT_1.webm`），
  迁移目录不影响解析（`--artifacts-dir` 决定根）
