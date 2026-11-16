"""pytest 共享配置：仓库根入 sys.path + 环境变量隔离。

**为什么要 pin 环境变量**：`studios/agent_utils.py` 在导入时会以 `override=False` 载入
仓库根 `.env` / 遗留 `ai-short-drama/.env`。若开发者本机有 `.env`（例如照 README
执行过 `cp .env.example .env` 并打开了 `SCENE_ENV=test`），测试结果会随本机配置变化——
`test_pipeline_e2e.py::test_no_key_non_demo_raises`、`test_edit_batch.py` 等依赖
「缺省 prod → NoKeyError」的用例会因后端变成 ollama 而失败。

因此这里在**导入任何被测模块之前**清空并固定相关环境变量，保证测试可重现。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── 环境隔离（必须早于任何 studios/schemas 导入）─────────────
# 清除可能来自 shell / .env 的两环境与渲染变量，让缺省值（prod → deepseek）生效。
for _var in (
    "SCENE_ENV",
    "SCENE_OLLAMA_MODEL",
    "SCENE_LLM_MODE",
    "SCENE_LLM_BACKEND",
    "SCENE_BACKEND_OVERRIDE",
    "SCENE_COMFY_BASE_URL",
    "SCENE_COMFY_OUTPUT",
    "SCENE_RENDER_CKPT",
    "SCENE_OLLAMA_BASE_URL",
    # DeepSeek 端点/模型也在 import 时解析（可能来自 shell 或 .env），不 pin 会令测试随环境变化
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
):
    os.environ.pop(_var, None)

# 彻底跳过 .env 自动加载（否则 agent_utils 导入时会把它重新注入，刚 pop 掉的变量又回来）。
os.environ["SCENE_SKIP_DOTENV"] = "1"