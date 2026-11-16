# sc-batching

分批 Agent 调用引擎：长文本一次生成会截断？按业务边界分批，**只重发失败批**。
纯 Python（仅 pydantic），**不依赖 SceneCraft 主仓**，可独立安装使用。

## 安装

```bash
pip install -e packages/sc-batching   # 仓库内可编辑安装
# 或发布后：pip install sc-batching
```

## 最小用法

```python
from sc_batching import count_batch_key, safe_parse_json

data = safe_parse_json('```json\n{"timeline": [1, 2, 3]}\n```')  # 自动剥代码围栏
print(count_batch_key(data, "timeline"))   # 3
```

分批调用需要一个「调用器」——任何带 `call_agent_json(agent, role, prompt)` 方法的对象
（鸭子类型，包不关心你用的是 DeepSeek / ollama / 其它）：

```python
from sc_batching import call_agent_json_batched

result = call_agent_json_batched(caller, "editor", "editor", prompts, merge_fn=merge)
```

## 内容

- `call_agent_json_batched(...)`：逐批调用 → 合并 → 整份契约校验；失败可定位批次
- `batch_validator(result, idx)`：批内校验，不合格只重发该批
- `count_batch_key` / `as_dict` / `group_shots_by_scene`：dict-safe 与同源分批
- `safe_parse_json` / `JSONParseError`：剥代码围栏，失败带原文 + 截断提示
- `NoKeyError`：用户可操作异常原样上抛，不重试

## 环境变量

无（key / 模型 / 超时全部由调用器负责）。
