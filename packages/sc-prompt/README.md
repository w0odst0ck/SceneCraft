# sc-prompt

提示词工程：按同源场景边界分批构建 prompter 输入，并把各批结果合并回一份
`PromptList` 契约（分批生成不改变最终产物结构）。
M0 抽包：由主仓 `studios/studio_prompt/run.py` 原样抽出纯函数部分，拼接顺序未改动。

M0 事实基线：六要素文本由 LLM 生成；demo 模式下的拼接仍在宿主
`agent_utils._demo_prompter`。方案里的 `build_shot_prompt(...)` 属 M1/M2 范围。

## 最小用法

```python
import json
from sc_prompt import build_prompt_batches, merge_prompt_lists

groups, batches = build_prompt_batches(shot_list, visual_bible, json.dumps(contract))
merged = merge_prompt_lists(results, default_model="Kling 2.0", default_aspect_ratio="16:9")
```

`append_contract` 可注入宿主的契约拼接函数（主仓传 `agent_utils.append_output_contract`）。
