"""sc_prompt.builders — prompter 分批输入构建 + 批次结果合并

M0 抽包：由 SceneCraft 仓库 `studios/studio_prompt/run.py` 原样抽出（纯函数，
拼接顺序/字段顺序与搬迁前完全一致，保证生成的 user_prompt 逐字节相同）。

说明（M0 事实基线）：六要素提示词文本由 LLM（prompter）生成，宿主
`studio_prompt/run.py` 只负责「按场景分批 + 契约注入 + 合并」；demo 模式下的
六要素字符串拼接仍在宿主 `agent_utils._demo_prompter`（任务书要求 demo 留原地）。
方案 §4.4 的 `build_shot_prompt(shot, bible, target)` 属 M1/M2 正式化范围。
"""
from __future__ import annotations

import json
from typing import Any, Callable


def _append_output_contract(user_prompt: str, contract_json: str) -> str:
    """默认契约注入（与宿主 studios.agent_utils.append_output_contract 逐字一致）。

    宿主调用 `build_prompt_batches` 时传入自己的 `append_output_contract`，
    保证单一真相源；包独立使用时可省略（用本默认实现）。
    """
    return (
        f"{user_prompt}\n\n"
        "【输出格式要求】严格只输出一个合法 JSON 对象，符合以下契约结构"
        "（字段名/类型必须一致，可调整具体内容）：\n"
        f"{contract_json}\n"
        "不要包含 Markdown 代码围栏、注释或任何多余文字。"
    )


def build_prompt_batches(
    shot_list: Any,
    visual_bible: Any,
    contract_json: str,
    append_contract: Callable[[str, str], str] | None = None,
) -> tuple[list[tuple[str, list[Any]]], list[str]]:
    """按同源场景边界构造 prompter 的每批 user_prompt。

    每批 = 本场镜头子集 + visual_bible 全量 + PromptList 契约文本；
    返回 (scene_groups, batches)，scene_groups 供调用方打印批次数。
    拼接顺序与搬迁前完全一致（dict 字段顺序、ensure_ascii、分隔符均不变）。
    """
    # 延迟导入：sc-prompt 仅依赖 sc-batching（依赖方向见 plan/插件化方案.md §3）
    from sc_batching import group_shots_by_scene

    append = append_contract or _append_output_contract
    scene_groups = group_shots_by_scene(shot_list)
    batches = [
        append(
            json.dumps({
                "shot_list": {
                    "target_shots": len(shots),
                    "shots": [s.model_dump(mode="json") for s in shots],
                },
                "visual_bible": visual_bible.model_dump(mode="json"),
            }, ensure_ascii=False),
            contract_json,
        )
        for _, shots in scene_groups
    ]
    return scene_groups, batches


def merge_prompt_lists(
    results: list[Any],
    default_model: str,
    default_aspect_ratio: str,
) -> dict[str, Any]:
    """合并各批 prompter 输出：prompts 按 shot_id 汇总，model / aspect_ratio 取首个非空值。

    dict-safe：raw safe_parse_json 可能返回顶层 list（非 dict）→ 取空 dict 跳过。
    """
    from sc_batching import as_dict

    prompts: dict[str, Any] = {}
    model: str | None = None
    aspect_ratio: str | None = None
    for res in results:
        # 类型防护：raw safe_parse_json 可能返回顶层 list（非 dict）→ 取空 dict 跳过
        data = as_dict(res)
        batch_prompts = data.get("prompts")
        if isinstance(batch_prompts, dict):
            prompts.update(batch_prompts)
        model = model or data.get("model")
        aspect_ratio = aspect_ratio or data.get("aspect_ratio")
    return {
        "model": model or default_model,
        "aspect_ratio": aspect_ratio or default_aspect_ratio,
        "prompts": prompts,
    }
