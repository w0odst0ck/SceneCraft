# sc-prompt

提示词工程：按同源场景边界分批构建 prompter 输入，并把各批结果合并回一份
`PromptList` 契约（分批生成不改变最终产物结构）。
**不依赖 SceneCraft 主仓**，可独立安装使用。

## 安装

```bash
# 仓库内：sc-prompt 依赖 sc-batching，两个一起装（本地未发布时 pip 无法自动解析）
pip install -e packages/sc-batching -e packages/sc-prompt
# 或发布后：pip install sc-prompt
```

## 最小用法

```python
from sc_prompt import merge_prompt_lists

batches = [
    {"model": "Kling 2.0", "aspect_ratio": "16:9",
     "prompts": {"SHOT_1": {"shot_id": "SHOT_1", "prompt": "雨夜便利店，中景缓慢推近"}}},
    {"prompts": {"SHOT_2": {"shot_id": "SHOT_2", "prompt": "雨幕中的霓虹街角"}}},
]
merged = merge_prompt_lists(batches, default_model="Kling 2.0", default_aspect_ratio="16:9")
print(merged["model"], merged["aspect_ratio"], len(merged["prompts"]))  # Kling 2.0 16:9 2
```

分批构建输入（`shot_list` / `visual_bible` 需提供 `.model_dump(mode="json")`，
可直接用 `sc-contracts` 的模型）：

```python
from sc_prompt import build_prompt_batches

groups, batches = build_prompt_batches(shot_list, visual_bible, contract_json)
```

`append_contract` 可注入自定义契约拼接函数；缺省使用包内精简版。

## 环境变量

无。

## 备注

六要素文本本身由 LLM 生成；本包只负责契约注入后的分批输入与合并
（拼接顺序与抽包前逐字节一致）。`build_shot_prompt(...)` 不在本包范围内。
