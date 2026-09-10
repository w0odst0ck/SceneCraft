"""studios/agent_utils.py — 各工作室 Agent 调用共享模块

从 v1 ai-short-drama/orchestration/pipeline.py 的 call_deepseek / AGENT_MODEL_MAP /
demo 分支逻辑参考移植并增强（不 import v1）：

- call_deepseek(): 真实 LLM 调用——按两环境路由：test（SCENE_ENV=test）走本地 ollama
  （¥0 开发/链路验证，超时放宽 300s），prod（缺省）走 DeepSeek（读 key → 超时 60s →
  失败重试 2 次指数退避）。返回 (text, usage)，JSON 解析交给各站（safe_parse_json 兜底）
- safe_parse_json(): 剥离 markdown 代码围栏、找第一个 JSON 块解析，失败抛 JSONParseError
- AgentCaller:    统一入口，真实模式走 call_deepseek，demo 模式返回内置演示输出；
                  累计每站 token 用量并换算成本（供 manifest 回填 cost_usd）
- call_agent_json(): 调用 + 解析 + 契约校验，解析失败自动重试 retries 次
- call_agent_json_batched(): 分批调用（按场景/镜头批）→ 逐批合并 → 整份契约校验，
  让链路对模型上下文规模不敏感（S2 分批生成）；单批失败定位到具体批次，merge 阶段
  失败说明合并范围（无法定位单批）；NoKeyError 等用户可操作异常原样上抛

DeepSeek 计价参考（2025-06 官方 deepseek-chat 按量计费，单位 USD / 1K tokens，
简化取整，供 manifest.cost_usd 粗算，非精确账单）：
    input  0.0014 USD / 1K tokens
    output 0.0028 USD / 1K tokens
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

# ── 两环境配置（唯一入口 SCENE_ENV=test|prod）────────────
# 语义：test = 本地 ollama（¥0 开发/链路验证）；prod = DeepSeek（成品质量）。
# 缺省 prod（保质量），测试环境显式切 test。后端由 SCENE_ENV 派生，不允许手设；
# 仅调试可用 SCENE_BACKEND_OVERRIDE 显式覆盖（旧 SCENE_LLM_BACKEND 兼容，见 _backend_override）。
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")  # 可用 DEEPSEEK_MODEL=deepseek-v4-flash 覆盖
SCENE_ENV_DEFAULT = "prod"                  # 缺省 prod：成品质量优先，测试显式切 test
ENV_TO_BACKEND = {"test": "ollama", "prod": "deepseek"}  # 环境 → 后端派生表
OLLAMA_DEFAULT_MODEL = "qwen3.5:9b"         # SCENE_OLLAMA_MODEL 缺省（本地快模型）
OLLAMA_CTX2K_MODEL = "qwen3:14b-ctx2k"      # ctx 2048 受限模型：max_tokens 须 < ctx（弃用过渡映射目标）
AGENT_MAX_TOKENS = 4096
REQUEST_TIMEOUT = 60          # prod DeepSeek 单次调用超时（秒）
OLLAMA_REQUEST_TIMEOUT = 300  # test ollama 本地生成慢，60s 会误杀 → 放宽（hotfix 保留）
RETRY_TIMES = 2               # 失败自动重试次数（指数退避，共尝试 RETRY_TIMES + 1 次）

def _request_timeout() -> int:
    """按后端放宽单次调用超时：ollama（test 本地）→ 300s；deepseek（prod）保持 60s。"""
    return OLLAMA_REQUEST_TIMEOUT if _resolve_backend() == "ollama" else REQUEST_TIMEOUT


def _scene_env() -> str:
    """读取唯一入口 SCENE_ENV=test|prod；缺省 prod（保质量），未知值回退 prod。"""
    env = os.getenv("SCENE_ENV", SCENE_ENV_DEFAULT).strip().lower()
    return env if env in ENV_TO_BACKEND else SCENE_ENV_DEFAULT


def _backend_override() -> str | None:
    """调试显式覆盖后端：SCENE_BACKEND_OVERRIDE=deepseek|ollama 优先于 SCENE_ENV 派生。

    兼容（弃用）：旧 SCENE_LLM_BACKEND 显式设为非默认值（ollama）时按 override 同等处理，
    老调用方不炸；显式 deepseek 即旧默认值，与新派生默认（prod→deepseek）一致，无需处理。
    """
    override = os.getenv("SCENE_BACKEND_OVERRIDE", "").strip().lower()
    if override in ("deepseek", "ollama"):
        return override
    if os.getenv("SCENE_LLM_BACKEND", "").strip().lower() == "ollama":
        return "ollama"
    return None


def _resolve_backend() -> str:
    """解析实际后端：override 优先 → SCENE_ENV 派生（test→ollama / prod→deepseek）。"""
    return _backend_override() or ENV_TO_BACKEND[_scene_env()]


def _ollama_model() -> str:
    """运行时直选本地模型：SCENE_OLLAMA_MODEL 优先，缺省 qwen3.5:9b。

    弃用过渡：SCENE_OLLAMA_MODEL 未设而旧 SCENE_LLM_MODE（test/prod）已设时，最后一次
    按其映射（test→qwen3.5:9b / prod→qwen3:14b-ctx2k）；两者均未设才用缺省。
    """
    model = os.getenv("SCENE_OLLAMA_MODEL", "").strip()
    if model:
        return model
    if os.getenv("SCENE_LLM_MODE", "").strip().lower() == "prod":
        return OLLAMA_CTX2K_MODEL
    return OLLAMA_DEFAULT_MODEL  # test / 未知 / 未设


def _ollama_base_url() -> str:
    base = (os.getenv("SCENE_OLLAMA_BASE") or "http://127.0.0.1:11434/v1").strip().rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def describe_environment() -> tuple[str, str, str]:
    """公共描述：返回 (env, backend, model) 解析结果，供 CLI 横幅 / 诊断打印。

    backend/model 与真实路由完全同源（同一套解析函数），避免各调用方自行推导不一致。
    """
    backend = _resolve_backend()
    model = _ollama_model() if backend == "ollama" else DEEPSEEK_MODEL
    return _scene_env(), backend, model

# 与 v1 一致的模型映射：默认 deepseek-chat，各 Agent 可单独覆盖
# ollama（test）后端时全部指向本地模型。注意：AGENT_MODEL_MAP 在 import 时解析一次
# （SCENE_ENV / SCENE_OLLAMA_MODEL 需 import 前设置，或写 .env 由 load_dotenv 先载入）；
# 实际请求路由在 call 时读 env（ollama 分支 effective_model = 显式 model or 运行时
# _ollama_model()）——ollama 分支不依赖 MAP 的值；deepseek 分支恒为 DEEPSEEK_MODEL，不受影响。
_AGENT_MODEL = _ollama_model() if _resolve_backend() == "ollama" else DEEPSEEK_MODEL
AGENT_MODEL_MAP: dict[str, str] = {
    "producer": _AGENT_MODEL,
    "writer": _AGENT_MODEL,
    "director": _AGENT_MODEL,
    "art_director": _AGENT_MODEL,
    "actor": _AGENT_MODEL,
    "cinematographer": _AGENT_MODEL,
    "editor": _AGENT_MODEL,
    "prompter": _AGENT_MODEL,
    "critic": _AGENT_MODEL,
}

# 计价常量（USD / 1K tokens），见模块顶部注释
PRICE_INPUT_PER_1K = 0.0014
PRICE_OUTPUT_PER_1K = 0.0028


class NoKeyError(Exception):
    """未配置 DEEPSEEK_API_KEY（环境变量与 ai-short-drama/.env 均缺失）。"""


def _looks_truncated(text: str) -> bool:
    """粗判输出是否被 max_tokens 截断：存在未闭合括号（开括号多于闭括号）。"""
    s = text or ""
    return s.count("{") > s.count("}") or s.count("[") > s.count("]")


class JSONParseError(Exception):
    """Agent 输出无法解析为合法 JSON，附带原文前 200 字供排错。

    增强（S2）：若输出疑似被 max_tokens 上限截断（有开括号无对应闭括号），
    额外附「疑似输出达 max_tokens（N）上限、可能被截断」诊断提示，
    便于定位 ctx 受限模型（如 qwen3:14b-ctx2k）的输出截断问题。
    """

    def __init__(self, reason: str, text: str = ""):
        self.reason = reason
        self.text = text or ""
        snippet = self.text[:200]
        message = f"{reason}；原文前 200 字：{snippet!r}"
        if _looks_truncated(self.text):
            message += (
                f"\n提示：疑似输出达 max_tokens（{_max_tokens()}）上限、可能被截断；"
                "建议减小单次输出规模（按场景/镜头分批生成）。"
            )
        super().__init__(message)


# ── Key 读取 ─────────────────────────────────────────────

def _env_path() -> Path:
    """ai-short-drama/.env 的绝对路径（agent_utils.py 位于 <root>/studios/）。"""
    return Path(__file__).resolve().parents[1] / "ai-short-drama" / ".env"


def get_api_key() -> str | None:
    """读取 DeepSeek key：优先环境变量 DEEPSEEK_API_KEY，其次 ai-short-drama/.env。"""
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    env_path = _env_path()
    if env_path.exists():
        load_dotenv(env_path)
        key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    return key or None


# ── 真实调用 ─────────────────────────────────────────────

def _max_tokens() -> int:
    """按 ollama + ctx 受限模型钳制输出上限：qwen3:14b-ctx2k（ctx 2048）必须 < ctx，否则超窗必失败。"""
    if _resolve_backend() == "ollama" and _ollama_model() == OLLAMA_CTX2K_MODEL:
        return 1500  # 留 500+ 余量给 system+user prompt
    return AGENT_MAX_TOKENS


def call_deepseek(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> tuple[str, dict[str, int]]:
    """调用 LLM Chat Completions，按两环境路由：test→本地 ollama；prod（缺省）→DeepSeek。

    - DeepSeek（prod）：未配置 key 抛 NoKeyError（由调用方决定 demo 还是报错）
    - ollama（test）：url=SCENE_OLLAMA_BASE/chat/completions、无 Authorization、
      model 按 SCENE_OLLAMA_MODEL 直选（缺省 qwen3.5:9b，兼容旧 SCENE_LLM_MODE 过渡）
    - 单次超时 _request_timeout()（deepseek 60s / ollama 300s），失败自动重试 RETRY_TIMES 次（指数退避）
    - 返回原始文本（不解析 JSON），usage 含 prompt_tokens / completion_tokens
    """
    if _resolve_backend() == "ollama":
        headers = {"Content-Type": "application/json"}
        url = f"{_ollama_base_url()}/chat/completions"
        effective_model = model or _ollama_model()  # honor 显式传参；缺省按 SCENE_OLLAMA_MODEL 运行时直选
    else:
        api_key = get_api_key()
        if not api_key:
            raise NoKeyError(
                "未配置 DEEPSEEK_API_KEY（环境变量与 ai-short-drama/.env 均缺失）。"
                "如需无 key 演示请使用 --demo；真实调用请在 ai-short-drama/.env 配置 key。"
            )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
        effective_model = model or AGENT_MODEL_MAP.get("producer", DEEPSEEK_MODEL)
    payload = {
        "model": effective_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": _max_tokens(),
        "temperature": 0.7,
    }

    last_exc: Exception | None = None
    for attempt in range(RETRY_TIMES + 1):
        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=_request_timeout(),
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            return content, {
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
            }
        except Exception as exc:  # 网络 / 超时 / HTTP / 响应结构异常统一重试
            last_exc = exc
            if attempt < RETRY_TIMES:
                time.sleep(2 ** attempt)  # 指数退避：1s、2s
    raise RuntimeError(
        f"{_resolve_backend()} 调用失败（已重试 {RETRY_TIMES} 次）：{last_exc}"
    ) from last_exc


# ── JSON 解析保护 ────────────────────────────────────────

def safe_parse_json(text: str, model: str | None = None) -> Any:
    """从 Agent 输出中稳健解析 JSON。

    处理：剥离 markdown 代码围栏（```json ... ```）、忽略围栏外杂讯、
    取第一个完整 JSON 对象/数组块。失败抛 JSONParseError（带原文前 200 字）。
    """
    if not isinstance(text, str) or not text.strip():
        raise JSONParseError("输出为空", text or "")
    t = text.strip()
    # 剥离 markdown 代码围栏
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    # 找第一个 JSON 块（{ 或 [ 开头），按出现先后逐个尝试
    positions = sorted(i for i in (t.find("{"), t.find("[")) if i != -1)
    if not positions:
        raise JSONParseError("未找到 JSON 对象/数组", text)
    decoder = json.JSONDecoder()
    for idx in positions:
        try:
            obj, _ = decoder.raw_decode(t[idx:])
            return obj
        except json.JSONDecodeError:
            continue
    raise JSONParseError(
        f"JSON 解析失败（model={model or 'unknown'}，已尝试 {len(positions)} 个候选块）", text
    )


# ── demo 演示输出（无 key 可跑全链）─────────────────────
# 从 v1 demo 分支移植并适配 v2 契约：producer→MissionPlan、writer→4 场景剧本、
# director→分镜、cinematographer/actor→摄影/表演参数、art_director→VisualBible、
# prompter→六要素提示词、editor→时间线、critic→质检报告。
# 所有 demo 输出均为合法 JSON 字符串，走与真实调用相同的解析/校验路径。

_DEMO_MODEL = "Kling 2.0"
_DEMO_ASPECT = "16:9"
_DEMO_FPS = 24
_CAMERA_MOVES = ["缓慢推近", "平移跟拍", "手持微晃", "固定", "缓慢拉远"]
_FOCAL_LENGTHS = ["35mm", "50mm", "24mm", "85mm", "35mm"]


def _demo_parse_input(user_prompt: str) -> dict[str, Any]:
    """demo 分支解析 user_prompt（可能内含 JSON 输入），失败返回空 dict。"""
    try:
        data = safe_parse_json(user_prompt)
        return data if isinstance(data, dict) else {}
    except JSONParseError:
        return {}


def demo_output(agent: str, user_prompt: str) -> str:
    """返回指定 Agent 的演示输出 JSON 字符串（demo 模式专用）。"""
    dispatcher = {
        "producer": _demo_producer,
        "writer": _demo_writer,
        "director": _demo_director,
        "art_director": _demo_art_director,
        "cinematographer": _demo_cinematographer,
        "actor": _demo_actor,
        "prompter": _demo_prompter,
        "editor": _demo_editor,
        "critic": _demo_critic,
    }
    fn = dispatcher.get(agent)
    if fn is None:
        return json.dumps({"error": f"未知 demo agent: {agent}"}, ensure_ascii=False)
    return json.dumps(fn(user_prompt), ensure_ascii=False)


def _demo_producer(user_prompt: str) -> dict[str, Any]:
    concept = (user_prompt or "").strip().splitlines()[0][:40] or "demo 概念"
    return {
        "concept": concept,
        "genre": "悬疑",
        "target_duration_sec": 60,
        "target_shots": 8,
        "tone": "cinematic",
        "aspect_ratio": _DEMO_ASPECT,
        "fps": _DEMO_FPS,
    }


def _demo_writer(user_prompt: str) -> dict[str, Any]:
    mp = _demo_parse_input(user_prompt)
    concept = (mp.get("concept") or "demo 概念")[:40]
    scenes = [
        {"scene_id": "SCENE_1", "location": "雨夜便利店", "time_of_day": "深夜",
         "summary": "神秘顾客深夜进店，主角察觉异常。",
         "dialogue": [{"speaker": "主角", "line": "「这么晚了，买什么？」"}],
         "emotional_arc": "平静 → 警觉", "duration_sec": 12.0},
        {"scene_id": "SCENE_2", "location": "便利店仓库", "time_of_day": "深夜",
         "summary": "主角追查顾客留下的物品，发现线索。", "dialogue": None,
         "emotional_arc": "警觉 → 疑惑", "duration_sec": 16.0},
        {"scene_id": "SCENE_3", "location": "便利店门口", "time_of_day": "凌晨",
         "summary": "神秘顾客折返，与主角对峙。",
         "dialogue": [
             {"speaker": "神秘顾客", "line": "「你在找的东西，不在货架上。」"},
             {"speaker": "主角", "line": "「你到底是谁？」"},
         ],
         "emotional_arc": "疑惑 → 紧张", "duration_sec": 18.0},
        {"scene_id": "SCENE_4", "location": "雨夜街角", "time_of_day": "凌晨",
         "summary": "真相浮现，主角做出选择。", "dialogue": None,
         "emotional_arc": "紧张 → 释然", "duration_sec": 14.0},
    ]
    return {
        "title": f"demo剧：{concept}",
        "logline": f"一个关于「{concept}」的短小悬疑故事。",
        "scenes": scenes,
        "emotional_curve": ["平静", "悬疑上升", "对峙高潮", "收束"],
    }


def _demo_director(user_prompt: str) -> dict[str, Any]:
    """demo 分镜：支持分批输入（单场 scene）与全量输入（script.scenes）两种形态。

    分批生成（S2）时每批 user_prompt 只含本场 `scene`，此处按单场产出该场镜头；
    大场细分组（shot_group.total > 1）时只返回本组应产出的那部分镜头——否则各组
    都会重复产出整场镜头、合并后同场镜头被复制（组内切片保证并集 = 全场、无重复）。
    未含 `scene` 时回退旧的整份 script（保持旧用法兼容）。
    """
    data = _demo_parse_input(user_prompt)
    scene = data.get("scene")
    if isinstance(scene, dict):
        scenes = [scene]  # 分批：本批单场
    else:
        script = data.get("script") or {}
        scenes = script.get("scenes") or []
    group = data.get("shot_group") if isinstance(data.get("shot_group"), dict) else {}
    try:
        group_total = max(1, int(group.get("total") or 1))
        group_index = max(1, int(group.get("index") or 1))
    except (TypeError, ValueError):
        group_total, group_index = 1, 1
    shots: list[dict[str, Any]] = []
    n = 0
    for scene in scenes:
        # 每场镜数：细分组数超过 3 时以组数为准（否则后面的组会切出空镜头、被空批次校验拦下）
        scene_shot_count = max(3, group_total) if group_total > 1 else 3
        scene_shots: list[dict[str, Any]] = []
        for i in range(scene_shot_count):  # 每场默认 3 镜
            n += 1
            scene_shots.append({
                "shot_id": f"SHOT_{n}",
                "scene_id": scene.get("scene_id", f"SCENE_{n}"),
                "duration": round(float(scene.get("duration_sec", 6.0)) / scene_shot_count, 2),
                "subject": "神秘顾客（深色风衣，兜帽遮脸）" if i == 0 else "主角（便利店店员）",
                "action": "进入店内环视" if i == 0 else "暗中观察/对峙",
                "emotion": scene.get("emotional_arc", "平静") or "平静",
                "environment": scene.get("location", "雨夜便利店"),
                "lighting": "冷色顶灯 + 窗外霓虹",
                "camera_angle": ["低角度仰拍", "平视中景", "过肩特写"][i % 3],
                "camera_movement": _CAMERA_MOVES[(n - 1) % len(_CAMERA_MOVES)],
                "focal_length": _FOCAL_LENGTHS[(n - 1) % len(_FOCAL_LENGTHS)],
                "narrative_purpose": f"场景{n}镜{i + 1}：推进剧情/交代细节",
            })
        if group_total > 1:  # 细分组：本组只取整场镜头的一段（shot_id 由合并阶段重写）
            per_group = (len(scene_shots) + group_total - 1) // group_total
            start = (group_index - 1) * per_group
            scene_shots = scene_shots[start:start + per_group]
        shots.extend(scene_shots)
    return {"target_shots": len(shots), "shots": shots}


def _demo_art_director(user_prompt: str) -> dict[str, Any]:
    data = _demo_parse_input(user_prompt)
    script = data.get("script") or {}
    title = script.get("title", "demo剧")
    return {
        "color_palette": {"primary": "#1a1a2e", "secondary": "#16213e",
                          "accent": "#e94560", "mood": "雨夜冷峻、克制悬疑"},
        "material_style": "湿润沥青 + 玻璃橱窗 + 冷白日光灯",
        "lighting_style": "冷色主光 + 霓虹点缀，高反差夜景",
        "character_designs": [
            {"character": "主角", "appearance": "便利店店员，年轻，深蓝工装",
             "costume": "深蓝便利店制服 + 反光背心", "color_key": "#4fa3ff"},
            {"character": "神秘顾客", "appearance": "高挑身形，兜帽遮住半脸",
             "costume": "黑色长款风衣", "color_key": "#e94560"},
        ],
        "art_notes": [f"{title}：雨夜便利店", "雨滴打在玻璃上的反光", "凌晨街角冷清"],
    }


def _demo_cinematographer(user_prompt: str) -> dict[str, Any]:
    data = _demo_parse_input(user_prompt)
    shot_list = data.get("shot_list") or data
    shots = shot_list.get("shots") or []
    out: dict[str, Any] = {}
    for i, shot in enumerate(shots):
        sid = shot.get("shot_id", f"SHOT_{i + 1}")
        out[sid] = {
            "camera_angle": shot.get("camera_angle", "平视中景"),
            "focal_length": shot.get("focal_length", "35mm"),
            "aperture": "f/1.8",
            "camera_movement": shot.get("camera_movement", "固定"),
            "lighting_setup": shot.get("lighting", "冷色顶灯 + 霓虹"),
            "depth_of_field": "浅景深（特写）" if "特写" in str(shot.get("camera_angle", "")) else "中景深",
        }
    return out


def _demo_actor(user_prompt: str) -> dict[str, Any]:
    data = _demo_parse_input(user_prompt)
    shot_list = data.get("shot_list") or data
    shots = shot_list.get("shots") or []
    out: dict[str, Any] = {}
    for i, shot in enumerate(shots):
        sid = shot.get("shot_id", f"SHOT_{i + 1}")
        out[sid] = {
            "expression": "警觉、微微皱眉",
            "body_language": "缓慢动作，手微颤" if i % 2 else "静止倾听",
            "emotional_subtext": shot.get("emotion", "平静"),
            "gaze_direction": "望向门外雨幕" if i % 2 else "直视对方",
        }
    return out


def _demo_prompter(user_prompt: str) -> dict[str, Any]:
    data = _demo_parse_input(user_prompt)
    shot_list = data.get("shot_list") or {}
    vb = data.get("visual_bible") or {}
    shots = shot_list.get("shots") or []
    prompts: dict[str, Any] = {}
    palette = (vb.get("color_palette") or {}).get("mood", "冷峻夜景")
    for i, shot in enumerate(shots):
        sid = shot.get("shot_id", f"SHOT_{i + 1}")
        prompts[sid] = {
            "shot_id": sid,
            "prompt": (
                f"{shot.get('camera_angle', '平视中景')}，{shot.get('camera_movement', '固定')}，"
                f"{shot.get('focal_length', '35mm')}焦段。主体：{shot.get('subject', '')}。"
                f"动作：{shot.get('action', '')}。情绪：{shot.get('emotion', '')}。"
                f"环境：{shot.get('environment', '')}。光影：{shot.get('lighting', '')}，{palette}。"
                f"画质：cinematic, photorealistic, 8k。"
            ),
            "negative_prompt": "卡通、过度曝光、模糊、低画质",
            "model": _DEMO_MODEL,
            "aspect_ratio": _DEMO_ASPECT,
        }
    return {"model": _DEMO_MODEL, "aspect_ratio": _DEMO_ASPECT, "prompts": prompts}


def _demo_shot_number(shot_id: Any) -> int:
    """从 SHOT_k 里取 k（解析失败回退 0）：demo 按**全局镜号**给转场/音频落点。"""
    try:
        return int(str(shot_id).rsplit("_", 1)[-1])
    except (TypeError, ValueError):
        return 0


def _demo_editor(user_prompt: str) -> dict[str, Any]:
    """demo 剪辑：兼容分批输入（S2，单场 shot 子集）与全量输入两种形态。

    分批时每批 user_prompt 只含本场镜头子集，本批输出的帧号仅是本批相对占位——
    调用方（studio_edit）合并阶段按全局镜头顺序由代码统一补 start_frame /
    end_frame / total_frames（不信模型自填跨批连续性），故此处帧号只需合法。
    """
    data = _demo_parse_input(user_prompt)
    shot_list = data.get("shot_list") or {}
    shots = shot_list.get("shots") or []
    timeline: list[dict[str, Any]] = []
    frame = 0
    for i, shot in enumerate(shots):
        sid = shot.get("shot_id", f"SHOT_{i + 1}")
        num = _demo_shot_number(sid)  # 全局镜号：分批合并后转场分布与全量一致
        dur_frames = max(1, int(round(float(shot.get("duration", 3.0)) * _DEMO_FPS)))
        timeline.append({
            "shot_id": sid,
            "start_frame": frame,
            "end_frame": frame + dur_frames,
            "transition_in": "Cut" if num <= 1 else ("Cross Dissolve" if num % 4 == 0 else "Cut"),
            "transition_out": "Cut",
            "audio_event": "雨声渐强" if num % 4 == 1 else None,
        })
        frame += dur_frames
    beats: list[dict[str, Any]] = []
    if timeline:
        # 每批只出本批落点；时间按全局镜号近似（合并阶段排序去重，避免分批后落点全挤在 0s）
        first_num = _demo_shot_number(timeline[0]["shot_id"])
        beats = [{"time_sec": float(max(0, first_num - 1)), "event": "雨声渐强"}]
    return {
        "target_fps": _DEMO_FPS,
        "timeline": timeline,
        "total_frames": frame,
        "audio_beats": beats,
    }


def _demo_critic(user_prompt: str) -> dict[str, Any]:
    data = _demo_parse_input(user_prompt)
    stage = data.get("stage", "script")
    return {
        "stage": stage,
        "total_score": 85.0,
        "findings": [
            {"severity": "suggestion", "location": "全局",
             "message": "demo 质检：整体达标，建议补强结尾情绪收束。"},
        ],
    }


# ── AgentCaller 统一入口 ─────────────────────────────────

class AgentCaller:
    """Agent 调用的统一入口：真实走 DeepSeek，demo 走内置演示输出。

    - call(agent, soul_name, user_prompt) -> str：返回 Agent 输出原文
      （真实模式为 DeepSeek 响应文本，demo 模式为内置演示 JSON）
    - 累计 usage 与成本，供 manifest 回填 cost_usd
    """

    def __init__(self, demo_mode: bool = False, soul_dir: str | Path | None = None):
        self.demo_mode = demo_mode
        self.soul_dir = Path(soul_dir) if soul_dir else None
        self.total_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        self.last_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}

    # 统计
    def cost_usd(self) -> float:
        """累计成本（美元）：按 input/output token 数 × 单价常量换算。"""
        return (
            self.total_usage["prompt_tokens"] / 1000 * PRICE_INPUT_PER_1K
            + self.total_usage["completion_tokens"] / 1000 * PRICE_OUTPUT_PER_1K
        )

    def last_cost(self) -> float:
        """最近一次调用的成本（美元）。"""
        return (
            self.last_usage["prompt_tokens"] / 1000 * PRICE_INPUT_PER_1K
            + self.last_usage["completion_tokens"] / 1000 * PRICE_OUTPUT_PER_1K
        )

    # 调用
    def _load_soul(self, soul_name: str) -> str:
        """读取 Agent SOUL（prompt 人设）文件；不存在时返回空串并警告。"""
        if self.soul_dir is None:
            return ""
        path = self.soul_dir / f"{soul_name}.md"
        if not path.exists():
            print(f"  ⚠ 未找到 SOUL 文件：{path}（使用空 system prompt）")
            return ""
        return path.read_text(encoding="utf-8")

    def call(self, agent: str, soul_name: str, user_prompt: str) -> str:
        """调用一个 Agent，返回输出原文（字符串）。"""
        print(f"  🤖 [{agent}]...", end=" ", flush=True)
        if self.demo_mode:
            print("(demo)")
            return demo_output(agent, user_prompt)
        system = self._load_soul(soul_name)
        text, usage = call_deepseek(
            system, user_prompt, model=AGENT_MODEL_MAP.get(agent, DEEPSEEK_MODEL)
        )
        self.total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        self.total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        self.last_usage = usage
        print("✅")
        return text


# ── 输出契约注入（Phase B.1）────────────────────────────

def append_output_contract(user_prompt: str, contract_json: str) -> str:
    """在 user_prompt 末尾追加输出格式契约示例，约束 Agent 输出结构。

    Phase B.1 背景：仅传输入 JSON 时模型自由发挥，导致缺字段 / 类型不符
    （如 time_of_day / emotional_arc 缺失）。统一策略：每个 Agent 调用点
    在 user_prompt 末尾注入本段格式参考，契约示例来自 schemas/ 契约类的
    demo 实例 dump（字段名/类型与契约一致），保证真实输出可过 pydantic 校验。
    """
    return (
        f"{user_prompt}\n\n"
        "【输出格式要求】严格只输出一个合法 JSON 对象，符合以下契约结构"
        "（字段名/类型必须一致，可调整具体内容）：\n"
        f"{contract_json}\n"
        "不要包含 Markdown 代码围栏、注释或任何多余文字。"
    )


# ── 带契约校验的调用（解析失败自动重试）──────────────────

def call_agent_json(
    caller: AgentCaller,
    agent: str,
    soul_name: str,
    user_prompt: str,
    model_class: type[BaseModel] | None = None,
    retries: int = 1,
) -> Any:
    """调用 Agent → safe_parse_json → 契约校验，解析/校验失败重试 retries 次。

    重试时重新调用 Agent 并要求严格输出 JSON；仍失败抛最后异常（不静默降级）。
    返回 dict（model_class=None）或 model_class 实例。
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            text = caller.call(agent, soul_name, user_prompt)
            data = safe_parse_json(text, model=agent)
            if model_class is None:
                return data
            return model_class.model_validate(data)
        except (JSONParseError, ValidationError) as exc:
            last_exc = exc
            if attempt >= retries:
                break
            user_prompt = (
                f"{user_prompt}\n\n【注意】上次输出无法解析为合法 JSON 或与契约不符。"
                "请严格只输出一个合法的 JSON 对象，不要包含 Markdown 代码围栏、注释或任何多余文字。"
            )
    assert last_exc is not None
    raise last_exc


# ── 分批调用（S2：分镜/提示词分批生成）────────────────────
# 背景：一次性全量生成时输入 + 输出共享模型上下文（ctx2k=2048），大项目必截断。
# 改为「按场景分批 + 合并」：每批复用 call_agent_json 的解析/重试/契约注入，
# 合并后再对整份结果做一次契约校验，保证最终产物结构不变。

def _count_batch_items(result: Any) -> int:
    """通用批次条目计数（进度打印用）：dict / list 取长度，其它按 1 计。"""
    if isinstance(result, (dict, list)):
        return len(result)
    return 1


def count_batch_key(result: Any, key: str) -> int:
    """批次结果里某个键的条目数（进度打印 count_fn 用，dict-safe）。

    背景（ocr medium）：每批 call_agent_json 未传 model_class → 结果是 raw
    safe_parse_json 输出，而它同时尝试 `{` / `[` 两种块，可能返回**顶层 list**；
    此时 `result.get(key)` 抛 AttributeError，且发生在 results.append 之后 →
    掩盖真实批次结果、中断整个 run。故 count_fn 一律走本函数做类型防护。
    """
    if isinstance(result, dict):
        value = result.get(key)
        if isinstance(value, (dict, list)):
            return len(value)
    return 0


def as_dict(result: Any) -> dict[str, Any]:
    """把批次结果规范为 dict（非 dict → 空 dict），供 merge 函数做 dict-safe 访问。

    与 count_batch_key 同源防护：模型可能吐顶层 list（raw safe_parse_json），
    merge 阶段取字段前先规范化，避免 AttributeError 掩盖批次结果。
    """
    return result if isinstance(result, dict) else {}


def group_shots_by_scene(
    shot_list: Any, max_shots_per_batch: int | None = None
) -> list[tuple[str, list[Any]]]:
    """按 scene_id 把镜头分组（保持首次出现顺序），供 shoot / prompt / edit 同源分批。

    入参可为 ShotList 实例（读 .shots 与 shot.scene_id）或 shot_list dict
    （{"shots": [{...}]}）——鸭子类型处理，避免 agent_utils 依赖 schemas。
    返回 [(scene_id, [本场镜头...]), ...]；批次边界即「逐场」，与剧本结构对齐。

    max_shots_per_batch 给定时，单场镜数超过该上限则继续按上限切分（大场细分，
    同一 scene_id 会出现多个**连续**批次），保证单次输入/输出规模可控
    （ctx 受限模型）；缺省 None 保持「一场一批」原语义。
    """
    if isinstance(shot_list, dict):
        raw_shots = shot_list.get("shots") or []

        def _scene_of(shot: Any) -> str:
            return str((shot or {}).get("scene_id") or "")
    else:
        raw_shots = getattr(shot_list, "shots", []) or []

        def _scene_of(shot: Any) -> str:
            return str(getattr(shot, "scene_id", "") or "")

    order: list[str] = []
    groups: dict[str, list[Any]] = {}
    for shot in raw_shots:
        sid = _scene_of(shot)
        if sid not in groups:
            groups[sid] = []
            order.append(sid)
        groups[sid].append(shot)
    if max_shots_per_batch is None or max_shots_per_batch < 1:
        return [(sid, groups[sid]) for sid in order]
    # 大场细分：本场镜头按上限切片成多个连续批次（scene_id 不变，仅批量变小）
    batches: list[tuple[str, list[Any]]] = []
    for sid in order:
        scene_shots = groups[sid]
        for start in range(0, len(scene_shots), max_shots_per_batch):
            batches.append((sid, scene_shots[start:start + max_shots_per_batch]))
    return batches


def call_agent_json_batched(
    caller: AgentCaller,
    agent: str,
    soul_name: str,
    batches: list[str],
    merge_fn: Callable[[list[Any]], Any],
    model_class: type[BaseModel] | None = None,
    retries: int = 1,
    count_fn: Callable[[Any], int] | None = None,
) -> Any:
    """分批调用 Agent → 逐批合并 → 整份契约校验（S2 分批生成的薄工具）。

    - batches：每批的 user_prompt（调用方按业务边界构造，含契约注入）
    - 每批复用 call_agent_json（既有解析/校验失败自动重试逻辑）
    - 全部批次完成后调 merge_fn(results) 合并，再对整份结果做 model_class 校验
      （model_class=None 时直接返回合并后的 dict）
    - 进度打印：「[批次 k/N] <agent> 完成（本批 X 条）」（本地模型慢，进度可见）；
      count_fn 须对结果做类型防护（每批结果是 raw safe_parse_json 输出，可能是
      顶层 list）——请用 count_batch_key，避免 AttributeError 掩盖批次结果
    - 失败策略（不静默降级）：
      * 单批失败 → RuntimeError 标注「第 k/N 批」+ 已完成批次（可定位到具体批次）
      * NoKeyError 等用户可操作异常 → **原样上抛**，不包装（否则各站 main() 的
        NoKeyError 分支走不到，用户看不到「未配 key / 用 --demo」提示）
      * merge 阶段失败 → RuntimeError 标注「merge 阶段、涉及全部 N 批」
        （merge_fn 合并全部批次后才发现问题，无法再定位到单个批次）
    """
    if not batches:
        raise RuntimeError(f"{agent} 分批调用失败：批次列表为空")
    total = len(batches)
    counter = count_fn or _count_batch_items
    results: list[Any] = []
    for idx, user_prompt in enumerate(batches, start=1):
        try:
            result = call_agent_json(caller, agent, soul_name, user_prompt, retries=retries)
        except NoKeyError:
            # 用户可操作异常（未配 DEEPSEEK_API_KEY）：原样上抛 → 各站 main() 的
            # NoKeyError 分支给出「配置 key 或改用 --demo」的提示（ocr medium 修复）
            raise
        except Exception as exc:  # 批次失败：包装为带批次定位的 RuntimeError
            done = "、".join(f"第 {i} 批" for i in range(1, idx)) or "无"
            raise RuntimeError(
                f"{agent} 第 {idx}/{total} 批失败（已完成批次：{done}；"
                f"已成功 {len(results)} 批）：{exc}"
            ) from exc
        results.append(result)
        print(f"[批次 {idx}/{total}] {agent} 完成（本批 {counter(result)} 条）")
    try:
        merged = merge_fn(results)
    except Exception as exc:
        # merge 阶段：merge_fn 一次合并全部 N 批，失败无法定位到单批 → 只报合并范围
        raise RuntimeError(
            f"{agent} 合并 {total} 批结果失败（merge 阶段，涉及全部 {total} 批）：{exc}"
        ) from exc
    if model_class is None:
        return merged
    try:
        return model_class.model_validate(merged)
    except ValidationError as exc:
        # 合并后契约校验失败：各批解析/校验均已单批通过，问题出在 merge 阶段，
        # 无法再定位到具体批次 → 消息说明失败阶段 + 涉及批次范围（共 N 批）
        raise RuntimeError(
            f"{agent} 合并后契约校验失败（merge 阶段，涉及全部 {total} 批）：{exc}"
        ) from exc
