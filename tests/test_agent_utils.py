"""studios/agent_utils 单元测试：safe_parse_json / call_deepseek 重试与 NoKeyError /
demo 模式 / call_agent_json 解析失败重试 / call_agent_json_batched 分批工具（S2b）。全程 mock，不触发真实网络。"""
import json

import pytest

from schemas.shot_list import ShotList
from studios import agent_utils as au


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


# ── call_deepseek 重试（mock requests.post，先失败后成功）─

class _FakeResp:
    """requests.Response 的替身：raise_for_status 通过 + json() 返回 payload。"""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_call_deepseek_retries_then_succeeds(monkeypatch):
    """前 2 次抛网络异常，第 3 次成功：自动重试 2 次并返回 (text, usage)。"""
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("boom")
        return _FakeResp({
            "choices": [{"message": {"content": "  你好  "}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })

    monkeypatch.setattr(au, "get_api_key", lambda: "sk-test")
    monkeypatch.setattr(au.requests, "post", fake_post)
    monkeypatch.setattr(au.time, "sleep", lambda s: None)  # 退避不真睡

    text, usage = au.call_deepseek("sys", "user")
    assert text == "你好"
    assert usage == {"prompt_tokens": 10, "completion_tokens": 5}
    assert calls["n"] == 3  # 初次 + 2 次重试


def test_call_deepseek_all_fail_raises(monkeypatch):
    """始终失败：重试耗尽后抛 RuntimeError（不静默降级）。"""
    monkeypatch.setattr(au, "get_api_key", lambda: "sk-test")
    monkeypatch.setattr(au.requests, "post", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("always")))
    monkeypatch.setattr(au.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        au.call_deepseek("sys", "user")


def test_call_deepseek_no_key_raises(monkeypatch):
    """无 key（环境变量与 .env 均缺失）抛 NoKeyError。"""
    monkeypatch.setattr(au, "get_api_key", lambda: None)
    with pytest.raises(au.NoKeyError):
        au.call_deepseek("sys", "user")


# ── demo 模式 ───────────────────────────────────────────

def test_demo_output_non_empty():
    """demo 模式：9 个 Agent 的演示输出均非空（无 key 可跑全链）。"""
    caller = au.AgentCaller(demo_mode=True)
    for agent in ["producer", "writer", "director", "art_director", "cinematographer",
                  "actor", "prompter", "editor", "critic"]:
        out = caller.call(agent, agent, "demo 输入")
        assert isinstance(out, str) and out.strip(), f"{agent} demo 输出为空"


def test_demo_cost_zero():
    """demo 模式无真实调用，成本恒为 0。"""
    caller = au.AgentCaller(demo_mode=True)
    caller.call("producer", "producer", "x")
    assert caller.cost_usd() == 0.0


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
            merge_fn=lambda results: {"bad": True},  # 缺 ShotList 必填字段
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


# ── demo 分镜：大场细分组不重复产出 ─────────────────────

def _director_group_payload(group_index: int, group_total: int) -> str:
    """构造 director 细分组 payload（本场 30s 触发细分场景），供 demo 分组测试。"""
    return json.dumps({
        "visual_bible": {},
        "scene": {"scene_id": "SCENE_1", "location": "地点", "time_of_day": "夜",
                  "summary": "概要", "emotional_arc": "平静 → 紧张", "duration_sec": 30.0},
        "shot_group": {"index": group_index, "total": group_total, "estimated_shots": 3},
    }, ensure_ascii=False)


def test_demo_director_subgroups_do_not_duplicate_shots():
    """demo 大场细分组：各组只产本组镜头，并集 == 整场、无重复（否则合并后镜头被复制）。"""
    groups = [json.loads(au.demo_output("director", _director_group_payload(i, 2)))
              for i in (1, 2)]
    shots_1, shots_2 = groups[0]["shots"], groups[1]["shots"]
    assert len(shots_1) == 2 and len(shots_2) == 1        # 每场 3 镜按 2 组切分 → 2 + 1
    assert all(s["scene_id"] == "SCENE_1" for s in shots_1 + shots_2)
    # 两组内容互不重复（narrative_purpose 编码了镜内序号）
    assert not ({s["narrative_purpose"] for s in shots_1}
                & {s["narrative_purpose"] for s in shots_2})


def test_demo_director_many_subgroups_never_empty():
    """细分组数 > 每场默认 3 镜时，demo 按组数扩镜，避免后面的组切出空镜头。"""
    outs = [json.loads(au.demo_output("director", _director_group_payload(i, 4)))
            for i in (1, 2, 3, 4)]
    assert all(len(o["shots"]) == 1 for o in outs)          # 4 镜 / 4 组 → 每组 1 镜，无空组
    purposes = [s["narrative_purpose"] for o in outs for s in o["shots"]]
    assert len(purposes) == len(set(purposes)) == 4         # 并集 = 全场、无重复


def test_demo_director_without_group_returns_full_scene():
    """未带 shot_group（逐场单批）时，demo 仍返回整场 3 镜（原分批语义不回归）。"""
    payload = json.dumps({
        "visual_bible": {},
        "scene": {"scene_id": "SCENE_2", "location": "地点", "time_of_day": "深夜",
                  "summary": "概要", "emotional_arc": "紧张", "duration_sec": 12.0},
    }, ensure_ascii=False)
    out = json.loads(au.demo_output("director", payload))
    assert out["target_shots"] == 3 and len(out["shots"]) == 3
