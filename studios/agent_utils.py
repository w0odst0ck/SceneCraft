"""studios/agent_utils.py — 各工作室 Agent 调用共享模块

M0 抽包：分批调用引擎（safe_parse_json / call_agent_json / call_agent_json_batched /
count_batch_key / as_dict / group_shots_by_scene / JSONParseError / NoKeyError）已迁至
`packages/sc-batching`（`sc_batching`），本模块从包导入并再导出，旧 import 路径不变；
本文件保留宿主相关部分：两环境解析、call_deepseek、demo 输出、AgentCaller、契约注入。

历史参考：ai-short-drama（v1，已弃用）orchestration/pipeline.py 的 call_deepseek /
AGENT_MODEL_MAP / demo 分支逻辑，参考移植并增强（不 import v1）：

- call_deepseek(): 真实 LLM 调用——按两环境路由：test（SCENE_ENV=test）走本地 ollama
  （¥0 开发/链路验证，超时放宽 300s），prod（缺省）走 DeepSeek（读 key → 超时 60s →
  失败重试 2 次指数退避）。返回 (text, usage)，JSON 解析交给各站（safe_parse_json 兜底）
- safe_parse_json(): 剥离 markdown 代码围栏、找第一个 JSON 块解析，失败抛 JSONParseError
- AgentCaller:    统一入口，真实模式走 call_deepseek，demo 模式返回内置演示输出；
                  累计每站 token 用量并换算成本（供 manifest 回填 cost_usd）
- call_agent_json(): 调用 + 解析 + 契约校验，解析失败自动重试 retries 次
- call_agent_json_batched(): 分批调用（按场景/镜头批）→ 逐批合并 → 整份契约校验，
  让链路对模型上下文规模不敏感（S2 分批生成）；单批失败定位到具体批次，merge 阶段
  失败说明合并范围（无法定位单批）；NoKeyError 等用户可操作异常原样上抛；
  batch_validator（S2c）可选：对每批输出做批内校验，不合格则**只重发该批**（batch_retries
  次），避免某批模型输出不全就把整个站拖挂——重试仍不合格再汇总报错（含批次号 + 缺失项）；
  S2d：**调用级失败**（空响应 / JSONParseError / 批级 RuntimeError 等）同样**只重发本批**，
  与校验不合格**共用同一 batch_retries 预算**（每轮 = 一次本批 call_agent_json，
  故单批最多 batch_retries + 1 轮，且不因两类失败叠加而翻倍）；仅 NoKeyError 原样上抛不重试

DeepSeek 计价参考（2025-06 官方 deepseek-chat 按量计费，单位 USD / 1K tokens，
简化取整，供 manifest.cost_usd 粗算，非精确账单）：
    input  0.0014 USD / 1K tokens
    output 0.0028 USD / 1K tokens

demo 输出（`_demo_*` / `demo_output`）：**仅服务主仓无 key 回归测试，不属于任何包**。
它们与主仓契约及站内分批输入形态强绑定（例如分镜细分组、剪辑帧号口径），
因此留在宿主而不下沉到 `packages/`；包使用者应自己提供 Agent 调用器或演示数据。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

# 分批调用引擎已抽包（M0）：从 sc_batching 导入并再导出，旧 import 路径保持有效
from sc_batching import (
    JSONParseError,
    NoKeyError,
    as_dict,
    batch_failure_hint,
    call_agent_json,
    call_agent_json_batched,
    count_batch_key,
    group_shots_by_scene,
    safe_parse_json,
    set_max_tokens_provider,
)

# ── .env 加载（M1：模块导入时一次性载入，供下文所有 os.getenv 生效）──
# 优先级：环境变量 > 仓库根 .env > 遗留 ai-short-drama/.env（v1，已弃用）。
# override=False：已存在的环境变量优先，不会被文件覆盖。
# SCENE_SKIP_DOTENV=1 时完全跳过（测试/CI 用：保证结果不随本机 .env 变化）。
_ROOT_DIR = Path(__file__).resolve().parents[1]
_ENV_CANDIDATES: tuple[Path, ...] = (
    _ROOT_DIR / ".env",                      # 标准位置（见仓库根 .env.example）
    _ROOT_DIR / "ai-short-drama" / ".env",   # v1 遗留位置，兼容兜底
)
_ENV_LOADED: Path | None = None
if os.getenv("SCENE_SKIP_DOTENV", "").strip() not in ("1", "true", "yes"):
    _ENV_LOADED = next((p for p in _ENV_CANDIDATES if p.exists()), None)
    if _ENV_LOADED is not None:
        load_dotenv(_ENV_LOADED, override=False)

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


# ── Key 读取 ─────────────────────────────────────────────

def _env_path() -> Path | None:
    """返回导入时实际加载的 .env 路径（无则 None）。

    单一真相源：与模块顶部的一次性加载保持一致，避免二次动态扫描导致不一致。
    """
    return _ENV_LOADED


def get_api_key() -> str | None:
    """读取 DeepSeek key：环境变量 DEEPSEEK_API_KEY 优先，其次根 .env / 遗留 ai-short-drama/.env。

    注：.env 已在模块导入时以 override=False 载入，此处不再重复 load_dotenv。
    """
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    return key or None


# ── 真实调用 ─────────────────────────────────────────────

def _max_tokens() -> int:
    """按 ollama + ctx 受限模型钳制输出上限：qwen3:14b-ctx2k（ctx 2048）必须 < ctx，否则超窗必失败。"""
    if _resolve_backend() == "ollama" and _ollama_model() == OLLAMA_CTX2K_MODEL:
        return 1500  # 留 500+ 余量给 system+user prompt
    return AGENT_MAX_TOKENS


# 把本模块的 max_tokens 解析（两环境派生 + ctx 受限模型钳制）注入 sc_batching：
# 保证 JSONParseError 截断诊断提示里的数值与搬迁前逐字一致（M0 权宜，M1 改为显式参数）。
set_max_tokens_provider(_max_tokens)


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
                "未配置 DEEPSEEK_API_KEY（环境变量与根 .env／遗留 ai-short-drama/.env 均缺失）。"
                "如需无 key 演示请使用 --demo；真实调用请在根 .env 配置 key（见 .env.example）。"
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
    帧号口径与契约一致（闭区间，S2d 统一）：end = start + 帧数 - 1、total = Σ 帧数。
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
            "end_frame": frame + dur_frames - 1,   # 闭区间：出点含端点
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


