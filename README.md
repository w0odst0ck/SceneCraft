# SceneCraft

**一句话概念 → 成套视频产物。** 一条拆成 7 个独立工作室的 AI 短剧流水线：随时停、改、续。

```
概念 → 剧本 → 美术 → 分镜 → 提示词 → 剪辑 → 渲染 → 质检
```

## 快速开始

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 跑通全链（无需 API key、无需 GPU）
python studios/run_pipeline.py --project demo --concept "雨夜便利店的神秘顾客" --demo
```

产物在 `artifacts/demo/`：`manifest.json`（台账）+ `01_script … 07_qc/`。

## 真实使用

```bash
cp .env.example .env          # 填 DEEPSEEK_API_KEY（生产环境）
source scripts/scene-env.sh test    # 测试环境：本地 ollama，¥0

python studios/run_pipeline.py \
    --project my-drama \
    --concept "雨夜便利店的神秘顾客" \
    --render                       # 真实渲染出视频
```

| 参数 | 作用 |
|---|---|
| `--concept` | 一句话创意 |
| `--from shoot` | 断点续跑：从任意站继续 |
| `--render` | 真实渲染出片（默认只出渲染计划） |
| `--render-limit N` | 只渲前 N 镜，快速验证 |
| `--qc` | 追加质检 |

## 独立包

每个包可单独安装使用，不依赖主仓：

| 包 | 解决什么 |
|---|---|
| `sc-contracts` | 产物契约 + 血缘（防 AI 覆盖人工修改） |
| `sc-batching` | 长文本分批生成 + 批内重试（防截断） |
| `sc-materials` | 素材卡库 + 版权三态闸 |
| `sc-prompt` | 六要素提示词构建 |
| `sc-render` | ComfyUI + LTX 视频渲染客户端 |

```bash
pip install -e packages/sc-batching
```

## 环境

- Python 3.11+
- 渲染需要 ComfyUI（`http://127.0.0.1:8188`）+ LTX 模型；不渲染则不需要
- `SCENE_ENV=test` 用本地 ollama（免费）· `prod` 用 DeepSeek

## 许可

MIT