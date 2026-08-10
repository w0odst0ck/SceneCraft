"""studios/agent_utils.py — 各工作室 Agent 调用共享模块

从 v1 ai-short-drama/orchestration/pipeline.py 的 call_deepseek / AGENT_MODEL_MAP /
demo 分支逻辑参考移植并增强（不 import v1）：

- call_deepseek(): 真实 DeepSeek 调用（读 key → 超时 60s → 失败重试 2 次指数退避），
  返回 (text, usage)，JSON 解析交给各站（safe_parse_json 兜底）
- safe_parse_json(): 剥离 markdown 代码围栏、找第一个 JSON 块解析，失败抛 JSONParseError
- AgentCaller:    统一入口，真实模式走 call_deepseek，demo 模式返回内置演示输出；
                  累计每站 token 用量并换算成本（供 manifest 回填 cost_usd）
- call_agent_json(): 调用 + 解析 + 契约校验，解析失败自动重试 retries 次

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
from typing import Any

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

# ── DeepSeek 配置 ────────────────────────────────────────
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")  # 可用 DEEPSEEK_MODEL=deepseek-v4-flash 覆盖
AGENT_MAX_TOKENS = 4096
REQUEST_TIMEOUT = 60          # 单次调用超时（秒）
RETRY_TIMES = 2               # 失败自动重试次数（指数退避，共尝试 RETRY_TIMES + 1 次）

# 与 v1 一致的模型映射：默认 deepseek-chat，各 Agent 可单独覆盖
AGENT_MODEL_MAP: dict[str, str] = {
    "producer": DEEPSEEK_MODEL,
    "writer": DEEPSEEK_MODEL,
    "director": DEEPSEEK_MODEL,
    "art_director": DEEPSEEK_MODEL,
    "actor": DEEPSEEK_MODEL,
    "cinematographer": DEEPSEEK_MODEL,
    "editor": DEEPSEEK_MODEL,
    "prompter": DEEPSEEK_MODEL,
    "critic": DEEPSEEK_MODEL,
}

# 计价常量（USD / 1K tokens），见模块顶部注释
PRICE_INPUT_PER_1K = 0.0014
PRICE_OUTPUT_PER_1K = 0.0028


class NoKeyError(Exception):
    """未配置 DEEPSEEK_API_KEY（环境变量与 ai-short-drama/.env 均缺失）。"""


class JSONParseError(Exception):
    """Agent 输出无法解析为合法 JSON，附带原文前 200 字供排错。"""

    def __init__(self, reason: str, text: str = ""):
        self.reason = reason
        snippet = (text or "")[:200]
        super().__init__(f"{reason}；原文前 200 字：{snippet!r}")


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

def call_deepseek(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> tuple[str, dict[str, int]]:
    """调用 DeepSeek Chat Completions，返回 (content, usage)。

    - 未配置 key 抛 NoKeyError（由调用方决定 demo 还是报错）
    - 单次超时 REQUEST_TIMEOUT（60s），失败自动重试 RETRY_TIMES 次（指数退避）
    - 返回原始文本（不解析 JSON），usage 含 prompt_tokens / completion_tokens
    """
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
    payload = {
        "model": model or AGENT_MODEL_MAP.get("producer", DEEPSEEK_MODEL),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": AGENT_MAX_TOKENS,
        "temperature": 0.7,
    }

    last_exc: Exception | None = None
    for attempt in range(RETRY_TIMES + 1):
        try:
            resp = requests.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
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
        f"DeepSeek 调用失败（已重试 {RETRY_TIMES} 次）：{last_exc}"
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
    data = _demo_parse_input(user_prompt)
    script = data.get("script") or {}
    scenes = script.get("scenes") or []
    shots: list[dict[str, Any]] = []
    n = 0
    for scene in scenes:
        for i in range(3):  # 每场 3 镜
            n += 1
            shots.append({
                "shot_id": f"SHOT_{n}",
                "scene_id": scene.get("scene_id", f"SCENE_{n}"),
                "duration": round(float(scene.get("duration_sec", 6.0)) / 3, 2),
                "subject": "神秘顾客（深色风衣，兜帽遮脸）" if i == 0 else "主角（便利店店员）",
                "action": "进入店内环视" if i == 0 else "暗中观察/对峙",
                "emotion": scene.get("emotional_arc", "平静") or "平静",
                "environment": scene.get("location", "雨夜便利店"),
                "lighting": "冷色顶灯 + 窗外霓虹",
                "camera_angle": ["低角度仰拍", "平视中景", "过肩特写"][i],
                "camera_movement": _CAMERA_MOVES[(n - 1) % len(_CAMERA_MOVES)],
                "focal_length": _FOCAL_LENGTHS[(n - 1) % len(_FOCAL_LENGTHS)],
                "narrative_purpose": f"场景{n}镜{i + 1}：推进剧情/交代细节",
            })
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


def _demo_editor(user_prompt: str) -> dict[str, Any]:
    data = _demo_parse_input(user_prompt)
    shot_list = data.get("shot_list") or {}
    shots = shot_list.get("shots") or []
    timeline: list[dict[str, Any]] = []
    frame = 0
    for i, shot in enumerate(shots):
        sid = shot.get("shot_id", f"SHOT_{i + 1}")
        dur_frames = max(1, int(round(float(shot.get("duration", 3.0)) * _DEMO_FPS)))
        timeline.append({
            "shot_id": sid,
            "start_frame": frame,
            "end_frame": frame + dur_frames,
            "transition_in": "Cut" if i == 0 else ("Cross Dissolve" if i % 3 == 0 else "Cut"),
            "transition_out": "Cut",
            "audio_event": "雨声渐强" if i % 4 == 0 else None,
        })
        frame += dur_frames
    beats = []
    if timeline:
        beats = [
            {"time_sec": round(timeline[0]["start_frame"] / _DEMO_FPS, 1), "event": "开场雨声"},
            {"time_sec": round(frame / 2 / _DEMO_FPS, 1), "event": "对峙鼓点"},
            {"time_sec": round(frame / _DEMO_FPS, 1), "event": "收束"},
        ]
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
