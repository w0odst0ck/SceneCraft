"""sc_batching 单元测试：JSON 解析 / call_agent_json 重试 / 分批工具（S2）与批内重试（S2c/S2d）。

M0 抽包：由主仓 tests/test_agent_utils.py 原样迁出（分批相关部分），用例逻辑未改；
仅两处适配：
- import：studios.agent_utils → sc_batching（以 `au` 别名保持用例写法不变）
- 契约模型：用等价最小 pydantic 模型代替 schemas.ShotList（包内不依赖宿主）
"""
import pytest
from pydantic import BaseModel

import sc_batching as au


class ShotList(BaseModel):
    """最小等价契约：只需「缺必填字段 → 校验失败」语义（原 schemas.ShotList）。"""

    target_shots: int
    shots: list[dict]


# ── safe_parse_json ─────────────────────────────────────

def test_safe_parse_json_with_markdown_fence():
    """markdown 代码围栏（```json ... ```）应被剥离。"""
    assert au.safe_parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert au.safe_parse_json('```\n[1, 2, 3]\n```') == [1, 2, 3]


def test_safe_parse_json_noise_around():
    """围栏外有杂讯时取第一个 JSON 块。"""
    assert au.safe_parse_json('好的，这是结果：{"b": [1, 2]} 完') == {"b": [1, 2]}


def test_safe_parse_json_bad_raises():
    """坏 JSON 抛 JSONParseError，且带原文前 200 字。"""
    with pytest.raises(au.JSONParseError) as excinfo:
        au.safe_parse_json("完全不是 JSON")
    assert "原文前 200 字" in str(excinfo.value)


def test_safe_parse_json_empty_raises():
    """空输出抛 JSONParseError。"""
    with pytest.raises(au.JSONParseError):
        au.safe_parse_json("   ")


# ── call_agent_json 解析失败重试 ────────────────────────

class _FakeCaller:
    """假 AgentCaller：按序吐出预设输出，记录每次 user_prompt。"""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls: list[str] = []

    def call(self, agent, soul, prompt):
        self.calls.append(prompt)
        return self.outputs[0] if len(self.outputs) == 1 else self.outputs.pop(0)


def test_call_agent_json_retries_on_parse_failure():
    """解析失败自动重试 1 次（重新调用 Agent），第二次成功。"""
    fake = _FakeCaller(["不是 JSON", '{"ok": true}'])
    result = au.call_agent_json(fake, "producer", "producer", "concept")
    assert result == {"ok": True}
    assert len(fake.calls) == 2
    assert "严格" in fake.calls[1]  # 重试提示要求严格 JSON


def test_call_agent_json_gives_up_after_retries():
    """重试仍失败：抛 JSONParseError，不静默降级。"""
    fake = _FakeCaller(["坏", "也坏"])
    with pytest.raises(au.JSONParseError):
        au.call_agent_json(fake, "producer", "producer", "concept", retries=1)
    assert len(fake.calls) == 2


# ── call_agent_json_batched：分批工具（S2/S2b）───────────

class _BatchCaller:
    """按序吐出预设输出的假 caller：元素为 Exception 时抛出，否则作原始文本返回。"""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls: list[str] = []

    def call(self, agent, soul, prompt):
        self.calls.append(prompt)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def test_count_batch_key_is_dict_safe():
    """count_batch_key：顶层 list / 缺键 / 非容器都安全（不与非 dict 的 .get 耦合）。"""
    assert au.count_batch_key([1, 2, 3], "timeline") == 0
    assert au.count_batch_key({"timeline": [1, 2]}, "timeline") == 2
    assert au.count_batch_key({"timeline": {"a": 1}}, "timeline") == 1
    assert au.count_batch_key({}, "timeline") == 0
    assert au.count_batch_key(None, "timeline") == 0
    assert au.count_batch_key("文本", "timeline") == 0


def test_group_shots_by_scene_subdivides_large_scene():
    """大场按 max_shots_per_batch 细分（同 scene_id 多个连续批次）；缺省保持一场一批。"""
    shot_list = {"shots": [
        {"shot_id": "SHOT_1", "scene_id": "SCENE_1"},
        {"shot_id": "SHOT_2", "scene_id": "SCENE_1"},
        {"shot_id": "SHOT_3", "scene_id": "SCENE_1"},
        {"shot_id": "SHOT_4", "scene_id": "SCENE_2"},
    ]}
    grouped = au.group_shots_by_scene(shot_list, max_shots_per_batch=2)
    assert [(sid, len(shots)) for sid, shots in grouped] == [
        ("SCENE_1", 2), ("SCENE_1", 1), ("SCENE_2", 1)]
    # 细分后镜头顺序不丢
    assert [s["shot_id"] for _, shots in grouped for s in shots] == [
        "SHOT_1", "SHOT_2", "SHOT_3", "SHOT_4"]
    assert [(sid, len(shots)) for sid, shots in au.group_shots_by_scene(shot_list)] == [
        ("SCENE_1", 3), ("SCENE_2", 1)]


def test_batched_count_fn_list_result_does_not_crash(capsys):
    """批次结果是顶层 list 时，进度打印不得抛 AttributeError（ocr medium 回归）。"""
    caller = _BatchCaller(['[1, 2]', '{"shots": [1, 2, 3]}'])
    out = au.call_agent_json_batched(
        caller, "director", "director", ["p1", "p2"],
        merge_fn=lambda results: {"merged": len(results)},
        count_fn=lambda res: au.count_batch_key(res, "shots"),
    )
    assert out == {"merged": 2}
    printed = capsys.readouterr().out
    assert "本批 0 条" in printed and "本批 3 条" in printed


def test_batched_reraises_nokey_error():
    """NoKeyError（未配 key）原样上抛，不被包装成「第 k/N 批失败」（ocr medium 回归）。"""
    caller = _BatchCaller([au.NoKeyError("未配置 DEEPSEEK_API_KEY")])
    with pytest.raises(au.NoKeyError):
        au.call_agent_json_batched(caller, "director", "director", ["p1"], merge_fn=lambda r: r)


def test_batched_wraps_batch_failure_with_index():
    """普通批次失败仍包装为带批次号的 RuntimeError（可定位到具体批次）。"""
    caller = _BatchCaller(["不是 JSON"])
    with pytest.raises(RuntimeError) as excinfo:
        au.call_agent_json_batched(caller, "director", "director", ["p1"],
                                   merge_fn=lambda r: r, retries=0)
    assert "第 1/1 批" in str(excinfo.value)


def test_batched_merge_fn_failure_reports_merge_scope():
    """merge_fn 抛错：消息说明失败发生在 merge 阶段 + 涉及全部 N 批（ocr low 回归）。"""
    caller = _BatchCaller(['{"a": 1}', '{"a": 2}'])
    with pytest.raises(RuntimeError) as excinfo:
        au.call_agent_json_batched(
            caller, "editor", "editor", ["p1", "p2"],
            merge_fn=lambda results: (_ for _ in ()).throw(ValueError("合并炸")),
        )
    message = str(excinfo.value)
    assert "merge 阶段" in message and "全部 2 批" in message and "合并炸" in message


def test_batched_merge_validation_failure_reports_scope():
    """合并后契约校验失败：消息说明 merge 阶段 + 涉及批次范围（ocr low 回归）。"""
    caller = _BatchCaller(['{"a": 1}', '{"a": 2}'])
    with pytest.raises(RuntimeError) as excinfo:
        au.call_agent_json_batched(
            caller, "director", "director", ["p1", "p2"],
            merge_fn=lambda results: {"bad": True},  # 缺契约必填字段
            model_class=ShotList,
        )
    message = str(excinfo.value)
    assert "merge 阶段" in message and "全部 2 批" in message


# ── call_agent_json_batched：批内校验 + 批内重试（S2c）────

def _has_items(result, idx):
    """批内校验替身：本批 dict 有非空 items → 合格（None），否则返回缺失说明。"""
    return None if au.as_dict(result).get("items") else "缺 1 条"


def test_batched_batch_validator_retries_only_bad_batch(capsys):
    """batch_validator 不合格的批只重发该批：合格批不受影响，重发后通过。"""
    # 第 1 批正常；第 2 批首次 items 空（校验未过）→ 只重发第 2 批 → 补齐
    caller = _BatchCaller(['{"items": [1]}', '{"items": []}', '{"items": [2]}'])
    out = au.call_agent_json_batched(
        caller, "editor", "editor", ["p1", "p2"],
        merge_fn=lambda results: {"total": sum(len(au.as_dict(r).get("items") or []) for r in results)},
        batch_validator=_has_items,
    )
    assert out == {"total": 2}
    assert len(caller.calls) == 3                        # 只第 2 批多发 1 次（合格批不重发）
    assert "不合格" in caller.calls[2]                    # 重试提示带「不合格」说明
    printed = capsys.readouterr().out
    assert "校验未过" in printed and "重试 1/2" in printed  # 进度日志：批次内重试可见


def test_batched_batch_validator_receives_batch_index():
    """batch_validator 收到 1-based 批序号（调用方据此定位本批应出内容）。"""
    seen: list[int] = []

    def _record(result, idx):
        seen.append(idx)
        return None

    caller = _BatchCaller(['{"items": [1]}', '{"items": [2]}'])
    au.call_agent_json_batched(caller, "editor", "editor", ["p1", "p2"],
                               merge_fn=lambda r: r, batch_validator=_record)
    assert seen == [1, 2]


def test_batched_batch_validator_exhausts_retries_raises():
    """批内校验反复不合格：汇总报错含批次号 + 缺失项，且总尝试 == batch_retries + 1。"""
    caller = _BatchCaller(['{"items": []}', '{"items": []}', '{"items": []}'])
    with pytest.raises(RuntimeError) as excinfo:
        au.call_agent_json_batched(
            caller, "editor", "editor", ["p1"],
            merge_fn=lambda r: r,
            batch_validator=lambda res, idx: "缺 SHOT_9",
        )
    message = str(excinfo.value)
    assert "第 1/1 批" in message and "缺 SHOT_9" in message
    assert "重试 2 次仍不合格" in message
    assert len(caller.calls) == 3                        # 总尝试 = 默认 batch_retries(2) + 1


def test_batched_batch_retries_zero_fails_fast():
    """batch_retries=0：批内校验不合格时不重发，立即汇总报错。"""
    caller = _BatchCaller(['{"items": []}'])
    with pytest.raises(RuntimeError):
        au.call_agent_json_batched(
            caller, "editor", "editor", ["p1"],
            merge_fn=lambda r: r, batch_validator=_has_items, batch_retries=0,
        )
    assert len(caller.calls) == 1


# ── call_agent_json_batched：调用级失败重试（S2d）─────────

def test_batched_retries_only_failed_batch_on_call_failure(capsys):
    """某批首次空响应（调用级失败）→ 只重发该批，合格批不重发，重试后成功（S2d）。"""
    # retries=0 关掉 call_agent_json 内部重试 → 空响应直接冒泡到批内重试
    caller = _BatchCaller(['{"items": [1]}', '', '{"items": [2]}'])
    out = au.call_agent_json_batched(
        caller, "editor", "editor", ["p1", "p2"],
        merge_fn=lambda results: {"total": sum(len(au.as_dict(r).get("items") or []) for r in results)},
        retries=0,
    )
    assert out == {"total": 2}
    assert len(caller.calls) == 3                        # 第 2 批多发 1 次（第 1 批不重发）
    assert caller.calls[0].startswith("p1") and caller.calls[1].startswith("p2")
    assert caller.calls[2].startswith("p2")              # 只重发失败那批
    assert "上次失败：输出为空" in caller.calls[2]         # 重试提示回灌失败原因，帮模型自纠
    printed = capsys.readouterr().out
    assert "调用失败（输出为空）" in printed and "重试 1/2" in printed


def test_batched_retries_call_failure_with_exception():
    """批级异常（非解析类，如网络/运行时）同样纳入批内重试，只重发该批。"""
    caller = _BatchCaller(['{"items": [1]}', RuntimeError("网络炸"), '{"items": [2]}'])
    out = au.call_agent_json_batched(
        caller, "editor", "editor", ["p1", "p2"],
        merge_fn=lambda results: {"total": sum(len(au.as_dict(r).get("items") or []) for r in results)},
        retries=0,
    )
    assert out == {"total": 2}
    assert "上次失败：调用异常（RuntimeError）" in caller.calls[2]


def test_batched_call_failure_exhausts_retries_raises():
    """连续调用级失败（空响应 / 非法 JSON）：重试耗尽 → 报错含批次号 + 原因 + 已完成批次。"""
    caller = _BatchCaller(['{"items": [1]}', '', '不是 JSON', ''])
    with pytest.raises(RuntimeError) as excinfo:
        au.call_agent_json_batched(
            caller, "editor", "editor", ["p1", "p2"],
            merge_fn=lambda r: r, retries=0, batch_retries=2,
        )
    message = str(excinfo.value)
    assert "第 2/2 批失败" in message and "重试 2 次仍失败" in message
    assert "输出为空" in message                          # 最后一次调用失败原因
    assert "已完成批次：第 1 批" in message                # 可定位：前面已成功哪些批
    assert len(caller.calls) == 4                        # 第 1 批 1 次 + 第 2 批 batch_retries+1 次


def test_batched_call_and_validation_share_retry_budget():
    """调用级失败与校验不合格共用同一 batch_retries 预算：交替失败也不翻倍，末次原因定汇总。"""
    caller = _BatchCaller(['', '{"items": []}', '{"items": []}'])
    with pytest.raises(RuntimeError) as excinfo:
        au.call_agent_json_batched(
            caller, "editor", "editor", ["p1"],
            merge_fn=lambda r: r, batch_validator=_has_items,
            retries=0, batch_retries=2,
        )
    assert len(caller.calls) == 3                        # = batch_retries + 1（共用预算）
    assert "校验未通过" in str(excinfo.value)             # 末次失败原因（校验不合格）决定汇总
