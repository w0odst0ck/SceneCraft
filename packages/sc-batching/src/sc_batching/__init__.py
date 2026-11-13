"""sc_batching — 分批 Agent 调用引擎（宿主无关）

M0 抽包：由 SceneCraft 仓库 `studios/agent_utils.py` 拆出分批相关部分，
分批 / 批内校验 / 调用级重试预算 / 截断诊断逻辑均未改动。

最小用法：
    from sc_batching import as_dict, call_agent_json_batched, count_batch_key
    result = call_agent_json_batched(
        caller, "director", "director", prompts,
        merge_fn=merge, model_class=ShotList,
        count_fn=lambda r: count_batch_key(r, "shots"),
    )
"""
from sc_batching.batching import (
    JSONParseError,
    NoKeyError,
    as_dict,
    batch_failure_hint,
    call_agent_json,
    call_agent_json_batched,
    count_batch_key,
    group_shots_by_scene,
    safe_parse_json,
    set_max_tokens_provider,
)

__all__ = [
    "call_agent_json",
    "call_agent_json_batched",
    "safe_parse_json",
    "JSONParseError",
    "NoKeyError",
    "count_batch_key",
    "as_dict",
    "group_shots_by_scene",
    "batch_failure_hint",
    "set_max_tokens_provider",
]
