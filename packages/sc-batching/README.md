# sc-batching

分批 Agent 调用引擎：长文本一次生成会截断？按业务边界分批，**只重发失败批**。
M0 抽包：由主仓 `studios/agent_utils.py` 原样拆出，分批/校验/重试逻辑未改动。

- `call_agent_json_batched(...)`：逐批调用 → 合并 → 整份契约校验；失败可定位批次
- `batch_validator(result, idx)`：批内校验，不合格只重发该批
- `count_batch_key` / `as_dict` / `group_shots_by_scene`：dict-safe 与同源分批
- `safe_parse_json` / `JSONParseError`：剥代码围栏，失败带原文 + 截断提示
- `NoKeyError`：用户可操作异常原样上抛，不重试

```python
from sc_batching import as_dict, call_agent_json_batched, count_batch_key

result = call_agent_json_batched(caller, "editor", "editor", prompts, merge_fn=merge,
                                 count_fn=lambda r: count_batch_key(r, "timeline"))
```

M0 权宜（待 M1 正式化）：`NoKeyError` 暂由包内定义、`set_max_tokens_provider()`
注入截断提示数值、`caller` 仍为鸭子类型（M1 改为注入式 `batch_call`）。
