"""studios/agent_utils 单元测试：safe_parse_json / call_deepseek 重试与 NoKeyError /
demo 模式 / call_agent_json 解析失败重试。全程 mock，不触发真实网络。"""
import pytest

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
