"""sc_prompt 单测：分批输入构建（字段/批序逐字节固定）+ 批次合并（dict-safe）。

M0 抽包：本测试为新增（原主仓无 studio_prompt 单测，仅 pipeline e2e 覆盖）；
用最小 duck-type 替身，不依赖宿主 schemas，保证包内 `pytest` 可独立通过。
"""
import json

from sc_prompt import build_prompt_batches, merge_prompt_lists
from sc_prompt.builders import _append_output_contract


class _Shot:
    """镜头替身：供 group_shots_by_scene 读 scene_id、build_prompt_batches 调 model_dump。"""

    def __init__(self, shot_id: str, scene_id: str):
        self.shot_id = shot_id
        self.scene_id = scene_id

    def model_dump(self, mode: str = "json") -> dict:
        return {"shot_id": self.shot_id, "scene_id": self.scene_id}


class _ShotList:
    def __init__(self, shots):
        self.shots = shots


class _VisualBible:
    def model_dump(self, mode: str = "json") -> dict:
        return {"color_palette": {"primary": "#1a1a2e"}}


def test_build_prompt_batches_order_and_bytes():
    """批次边界 = 场景首次出现顺序；每批 payload 字段顺序/序列化参数逐字节固定。"""
    shot_list = _ShotList([
        _Shot("SHOT_1", "SCENE_1"),
        _Shot("SHOT_2", "SCENE_1"),
        _Shot("SHOT_3", "SCENE_2"),
    ])
    contract = '{"contract": true}'
    groups, batches = build_prompt_batches(
        shot_list, _VisualBible(), contract,
        append_contract=lambda prompt, c: prompt + "||" + c,
    )
    assert [sid for sid, _ in groups] == ["SCENE_1", "SCENE_2"]
    assert [len(shots) for _, shots in groups] == [2, 1]
    expected_first = json.dumps({
        "shot_list": {
            "target_shots": 2,
            "shots": [
                {"shot_id": "SHOT_1", "scene_id": "SCENE_1"},
                {"shot_id": "SHOT_2", "scene_id": "SCENE_1"},
            ],
        },
        "visual_bible": {"color_palette": {"primary": "#1a1a2e"}},
    }, ensure_ascii=False) + "||" + contract
    assert batches[0] == expected_first
    assert len(batches) == 2


def test_default_append_contract_text_is_stable():
    """未注入宿主的拼接函数时，默认契约注入文本与主仓逐字一致（便于包独立使用）。"""
    out = _append_output_contract("BODY", '{"a": 1}')
    assert out == (
        "BODY\n\n"
        "【输出格式要求】严格只输出一个合法 JSON 对象，符合以下契约结构"
        "（字段名/类型必须一致，可调整具体内容）：\n"
        '{"a": 1}\n'
        "不要包含 Markdown 代码围栏、注释或任何多余文字。"
    )


def test_merge_prompt_lists_dedupes_and_falls_back():
    """prompts 按 shot_id 汇总（后批覆盖）；model/aspect_ratio 取首个非空，缺失用默认值。"""
    results = [
        [1, 2],  # 顶层 list（raw safe_parse_json 的异常形态）→ 跳过，不崩
        {"model": None, "aspect_ratio": "16:9",
         "prompts": {"SHOT_1": {"prompt": "a"}}},
        {"model": "Kling 2.0", "prompts": {"SHOT_1": {"prompt": "b"}, "SHOT_2": {"prompt": "c"}}},
    ]
    merged = merge_prompt_lists(results, default_model="DEFAULT", default_aspect_ratio="9:16")
    assert merged == {
        "model": "Kling 2.0",
        "aspect_ratio": "16:9",
        "prompts": {"SHOT_1": {"prompt": "b"}, "SHOT_2": {"prompt": "c"}},
    }


def test_merge_prompt_lists_uses_defaults_when_all_missing():
    """所有批都缺 model/aspect_ratio → 用调用方给的默认值（原 PromptList.demo() 取值）。"""
    merged = merge_prompt_lists([{}], default_model="Kling 2.0", default_aspect_ratio="16:9")
    assert merged == {"model": "Kling 2.0", "aspect_ratio": "16:9", "prompts": {}}
