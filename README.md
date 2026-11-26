# 🎬 SceneCraft

> **AI 短剧生产工具包** — 产物契约 + 分批生成 + 素材库 + 本地视频渲染。
> 可作为独立库使用，也可作为一条完整流水线跑通「概念 → 视频」。

📖 **产品说明书**：[`docs/产品说明书.md`](docs/产品说明书.md)（工作流 / 参数 / 运维 / 迭代方向）
📝 **项目复盘**：[`docs/SceneCraft-复盘-2026-11-26.md`](docs/SceneCraft-复盘-2026-11-26.md)（4 个半月的时间线 / 资产盘点 / 教训）
🧪 测试台账：[`test-results/README.md`](test-results/README.md)

---

## 这是什么

一条把「一句话概念」变成「成套视频产物」的流水线，拆成 7 个独立工作室，站间只通过**显式落盘的产物契约**通信——随时停、改、续。

```
概念 concept
  ↓
① 剧本 → ② 美术 → ③ 分镜 → ④ 提示词 → ⑤ 剪辑 → ⑥ 渲染 → ⑦ 质检
 script    visual    shot     prompt     editing    video      qc
           bible     list     list       blueprint  (.webm)
```

配套的**独立包**（可与本流水线无关地使用）：

| 包 | 解决什么 |
|---|---|
| `sc-contracts` | 产物契约 + 血缘（`upstream_hash` / `edited_by` / `version`） |
| `sc-batching` | 长文本一次生成会截断？按业务边界分批，**只重发失败批** |
| `sc-materials` | 素材卡库 + **版权三态闸**（原创/灵感/改写，fail-closed） |
| `sc-prompt` | 六要素提示词构建（主体/动作/环境/光照/运镜/情绪） |
| `sc-render` | ComfyUI + LTX-Video 本地渲染（内建显存纪律） |

---

## 快速开始

```bash
# 1. 环境（Python 3.11+）
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt    # 含五个本地包（editable）

# 2. 配置（可选：不配也能用 --demo 跑通全链）
cp .env.example .env                   # 填 DEEPSEEK_API_KEY（prod 环境用）

# 3. 跑一条完整链路（最简：演示模式，无需任何 key / GPU）
python studios/run_pipeline.py \
    --project my-first-drama \
    --concept "雨夜便利店的神秘顾客" \
    --demo \
    --artifacts-dir test-results/

# 4. 测试环境真实跑（本地 ollama，¥0）
source scripts/scene-env.sh test
python studios/run_pipeline.py --project t1 --concept "雨夜便利店的神秘顾客" \
    --material-tags 悬疑,雨夜 --artifacts-dir test-results/

# 5. 真实渲染出片（需 ComfyUI + LTX 模型）
python studios/run_pipeline.py --project t1 --from render --render --artifacts-dir test-results/
```

产物落在 `<artifacts-dir>/<project_id>/`：`manifest.json`（台账+血缘）+ `01_script … 07_qc/`。

---

## 核心特性

- **断点续跑**：`--from shoot` 从任意站继续，已完成产物保留
- **人工保护**：`edited_by: human` 的产物，AI 重跑不静默覆盖
- **两环境**：`SCENE_ENV=test`（本地 ollama，¥0）/ `prod`（DeepSeek，成品质量）
- **分批生成**：长产物按场景分批 + 批内校验 + 逐批重试（防截断/静默缺失）
- **本地渲染**：LTX-Video 2B via ComfyUI，12GB 显存可跑（~47s/镜）

---

## 目录

```
studios/          7 个工作室（每站独立可运行）
packages/         5 个独立包（宿主无关，可 pip install）
schemas/          契约薄转发层（实现已移至 packages/sc-contracts）
story-materials/  素材卡（22 张）+ 模板（6 类）
scripts/          工具（渲染客户端 / 显存调度 / 环境切换）
tests/            140 个测试
docs/             产品说明书 + 项目复盘
archive/          已归档（上游三件套 / 旧测试产物 / plan+memory 原始记录）
```

---

## 已知边界

| 项 | 现状 |
|---|---|
| **画质** | 本地 LTX 2B = **测试档**（语义偏模糊）；成品需走 API（minimax / 云 GPU） |
| **音频** | 未接入（配音/配乐/口型） |
| **QC** | 站已实现，需显式 `--qc` |
| **显存** | 渲染须独占 GPU（脚本自动卸载 ollama） |

---

## 许可证

MIT