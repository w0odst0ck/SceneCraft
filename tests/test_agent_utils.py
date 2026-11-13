"""studios/agent_utils 单元测试（主仓部分）：call_deepseek 重试与 NoKeyError / demo 模式 /
demo 分镜细分组。全程 mock，不触发真实网络。

M0 抽包：safe_parse_json / call_agent_json* / 分批工具（S2b/S2c/S2d）用例已迁至
packages/sc-batching/tests/test_batching.py；文件末尾转发收集（用例只有一份）。
"""
import json

import pytest

from studios import agent_utils as au


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


# ── M0 抽包：转发包内分批用例（用例只有一份，主仓 pytest 覆盖不减少）──
from _pkg_test_loader import load_tests  # noqa: E402

load_tests("sc-batching", "test_batching.py")
