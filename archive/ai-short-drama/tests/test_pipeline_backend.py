"""pipeline 双后端单测：ollama 分支请求构造（×2 mode）+ DeepSeek 默认分支回归。

全部 mock requests.post，断言 url/headers/body，不触碰真实网络/ollama。
运行: cd ai-short-drama && ../.venv/bin/python -m pytest tests/ -q
"""
import pytest

import orchestration.pipeline as pipeline

OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "  hi  "}}]}


@pytest.fixture(autouse=True)
def _clean_scene_llm_env(monkeypatch):
    """每个用例起点干净：删除可能泄漏的 SCENE_LLM_* 环境变量。"""
    for key in ("SCENE_LLM_BACKEND", "SCENE_LLM_MODE", "SCENE_OLLAMA_BASE"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def capture_post(monkeypatch):
    """替换 pipeline.requests.post，记录调用并返回假响应。"""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        calls.append({"url": url, "headers": headers,
                      "body": json, "timeout": timeout})
        return _FakeResponse()

    monkeypatch.setattr(pipeline.requests, "post", fake_post)
    return calls


def _system_message(body):
    return next(m for m in body["messages"] if m["role"] == "system")


def test_ollama_mode_test_request_shape(capture_post, monkeypatch):
    """backend=ollama + mode=test（缺省 SCENE_OLLAMA_BASE）：
    url=ollama /v1/chat/completions、无 Authorization、model=qwen3.5:9b。"""
    monkeypatch.setenv("SCENE_LLM_BACKEND", "ollama")
    monkeypatch.setenv("SCENE_LLM_MODE", "test")

    result = pipeline.call_deepseek("sys", "usr")

    assert result == "hi"
    assert len(capture_post) == 1
    call = capture_post[0]
    assert call["url"] == OLLAMA_URL
    assert "Authorization" not in call["headers"]
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["body"]["model"] == "qwen3.5:9b"
    assert _system_message(call["body"])["content"] == "sys"
    assert call["body"]["messages"][1] == {"role": "user", "content": "usr"}
    assert call["body"]["max_tokens"] == pipeline.AGENT_MAX_TOKENS
    assert call["timeout"] == 120


def test_ollama_mode_prod_request_shape(capture_post, monkeypatch):
    """backend=ollama + mode=prod → model=qwen3:14b-ctx2k（忽略实参 model）。"""
    monkeypatch.setenv("SCENE_LLM_BACKEND", "ollama")
    monkeypatch.setenv("SCENE_LLM_MODE", "prod")

    pipeline.call_deepseek("sys", "usr", model="ignored-model")

    call = capture_post[0]
    assert call["url"] == OLLAMA_URL
    assert "Authorization" not in call["headers"]
    assert call["body"]["model"] == "qwen3:14b-ctx2k"


def test_ollama_base_without_v1_is_normalized(capture_post, monkeypatch):
    """SCENE_OLLAMA_BASE 未带 /v1 时自动补全为 /v1/chat/completions。"""
    monkeypatch.setenv("SCENE_LLM_BACKEND", "ollama")
    monkeypatch.setenv("SCENE_LLM_MODE", "test")
    monkeypatch.setenv("SCENE_OLLAMA_BASE", "http://127.0.0.1:11434")

    pipeline.call_deepseek("sys", "usr")

    assert capture_post[0]["url"] == OLLAMA_URL


def test_deepseek_default_backend_unchanged(capture_post, monkeypatch):
    """无 SCENE_LLM_* env（缺省 deepseek）→ 行为与旧版一致：
    DeepSeek url、Bearer Authorization、body model=实参 model。"""
    monkeypatch.delenv("SCENE_LLM_BACKEND", raising=False)

    result = pipeline.call_deepseek("sys", "usr", model="deepseek-chat")

    assert result == "hi"
    call = capture_post[0]
    assert call["url"] == f"{pipeline.DEEPSEEK_BASE_URL}/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {pipeline.DEEPSEEK_API_KEY}"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["body"]["model"] == "deepseek-chat"


def test_agent_model_map_has_all_agents():
    """AGENT_MODEL_MAP 覆盖全部 9 个 agent 且取值一致（同后端同模型）。"""
    expected = {
        "producer", "writer", "director", "art_director", "actor",
        "cinematographer", "editor", "prompter", "critic",
    }
    assert set(pipeline.AGENT_MODEL_MAP) == expected
    assert len(set(pipeline.AGENT_MODEL_MAP.values())) == 1
def test_ollama_backend_no_key_not_demo(_clean_scene_llm_env, monkeypatch):
    """ollama 后端 + 无 DEEPSEEK_API_KEY → 不降级 demo（ocr finding 修复）。"""
    monkeypatch.setenv("SCENE_LLM_BACKEND", "ollama")
    monkeypatch.setattr(pipeline, "DEEPSEEK_API_KEY", "")
    r = pipeline.ShortDramaPipeline(concept="x")
    assert r.demo_mode is False


def test_deepseek_no_key_is_demo(_clean_scene_llm_env, monkeypatch):
    """deepseek 后端 + 无 key → 保持 demo 降级（默认行为不变）。"""
    monkeypatch.setattr(pipeline, "DEEPSEEK_API_KEY", "")
    r = pipeline.ShortDramaPipeline(concept="x")
    assert r.demo_mode is True
