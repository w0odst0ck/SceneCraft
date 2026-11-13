"""sc_prompt — 提示词工程（分批输入构建 + 批次合并）

M0 抽包：由 SceneCraft 仓库 `studios/studio_prompt/run.py` 原样抽出纯函数部分。
六要素文本本身由 LLM 生成；本包负责契约注入后的分批输入与合并（逐字节不变）。

最小用法：
    from sc_prompt import build_prompt_batches, merge_prompt_lists
    groups, batches = build_prompt_batches(shot_list, visual_bible, contract_json)
"""
from sc_prompt.builders import build_prompt_batches, merge_prompt_lists

__all__ = ["build_prompt_batches", "merge_prompt_lists"]
