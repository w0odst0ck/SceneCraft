"""sc_batching — 分批 Agent 调用引擎（S2 分批生成的薄工具，宿主无关）

M0 抽包：由 SceneCraft 仓库 `studios/agent_utils.py` 原样拆出分批相关部分，
分批 / 批内校验 / 调用级重试的合并预算 / 截断诊断逻辑均未改动。

公开符号：
    JSONParseError, NoKeyError, safe_parse_json
    call_agent_json, call_agent_json_batched
    count_batch_key, as_dict, group_shots_by_scene, batch_failure_hint
    set_max_tokens_provider

M0 权宜（留待 M1 正式化）：
- `NoKeyError` 暂在包内定义（原属 agent_utils），主仓从本包导入以保证异常是同一个类；
  M1 应改为调用方注入 / `except_reraises: tuple[type, ...]` 参数化。
- `JSONParseError` 的截断提示需要 max_tokens 数值（原宿主按两环境钳制），
  这里用 `set_max_tokens_provider()` 注入取值来源；未注入时用通用默认 4096。
  M1 应改为显式参数。
- `call_agent_json*` 的 caller 仍是鸭子类型（Any），包不知道 DeepSeek/ollama 存在。
"""
from __future__ import annotations

import json
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


class NoKeyError(Exception):
    """未配置 LLM API key（DEEPSEEK_API_KEY 环境变量 / .env 文件均缺失）。"""


# ── max_tokens 取值来源注入（M0 权宜，见模块 docstring）────────

_MAX_TOKENS_DEFAULT = 4096
_max_tokens_provider: Callable[[], int] | None = None


def set_max_tokens_provider(fn: Callable[[], int] | None) -> None:
    """注入 max_tokens 取值来源（截断诊断提示用）；传 None 恢复默认。"""
    global _max_tokens_provider
    _max_tokens_provider = fn


def _max_tokens() -> int:
    """当前输出上限（仅用于截断诊断提示；未注入时用通用默认值）。"""
    if _max_tokens_provider is None:
        return _MAX_TOKENS_DEFAULT
    return _max_tokens_provider()


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


# ── 带契约校验的调用（解析失败自动重试）──────────────────

def call_agent_json(
    caller: Any,
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


def batch_failure_hint(exc: Exception) -> str:
    """批内调用失败的简短原因：回灌给模型自纠（重试提示）+ 汇总报错（含批次号）共用。

    - 空响应 / JSON 解析失败（JSONParseError）：细分为「输出为空」「解析失败」
      （JSONParseError.reason 由 safe_parse_json 给出，如 "输出为空" / "未找到 JSON 对象/数组"）
    - 其它异常（网络/批级 RuntimeError 等）：按异常类型名给出简短说明
    """
    if isinstance(exc, JSONParseError):
        reason = exc.reason or ""
        return "输出为空" if "输出为空" in reason else f"解析失败（{reason}）"
    return f"调用异常（{type(exc).__name__}）"


def _batch_retry_prompt(user_prompt: str, reason: str) -> str:
    """构造批内重试提示：把失败原因回灌给模型帮助自纠。

    一律以**原始** user_prompt 为基底拼接（不叠加历次提示），避免多次重试后
    提示语层层嵌套、上下文膨胀。
    """
    return (
        f"{user_prompt}\n\n【注意】{reason}。"
        "请重新完整输出本批的合法 JSON 对象（不要代码围栏或多余文字）。"
    )


def call_agent_json_batched(
    caller: Any,
    agent: str,
    soul_name: str,
    batches: list[str],
    merge_fn: Callable[[list[Any]], Any],
    model_class: type[BaseModel] | None = None,
    retries: int = 1,
    count_fn: Callable[[Any], int] | None = None,
    batch_validator: Callable[[Any, int], str | None] | None = None,
    batch_retries: int = 2,
) -> Any:
    """分批调用 Agent → 逐批合并 → 整份契约校验（S2 分批生成的薄工具）。

    - batches：每批的 user_prompt（调用方按业务边界构造，含契约注入）
    - 每批复用 call_agent_json（既有解析/校验失败自动重试逻辑）
    - 全部批次完成后调 merge_fn(results) 合并，再对整份结果做 model_class 校验
      （model_class=None 时直接返回合并后的 dict）
    - 进度打印：「[批次 k/N] <agent> 完成（本批 X 条）」（本地模型慢，进度可见）；
      count_fn 须对结果做类型防护（每批结果是 raw safe_parse_json 输出，可能是
      顶层 list）——请用 count_batch_key，避免 AttributeError 掩盖批次结果
    - batch_validator（S2c，可选）：`f(本批结果, 批序号[1-based]) -> 错误消息 str | None`。
      对每批结果做批内校验；返回错误消息即判定不合格 → **只重发该批**（带「上次缺失 X，
      请补全」提示），最多 batch_retries 次；重试仍不合格则汇总报错（含批次号 + 缺失项）。
      校验通过（None）则收下本批。缺省 None = 不做批内校验（向后兼容）。
    - 批内重试预算（S2d）：**调用级失败与校验不合格共用同一 batch_retries 预算**——
      每轮尝试 = 一次本批 call_agent_json（调用级失败或校验不合格都消耗一轮），
      故单批最多 batch_retries + 1 轮（每轮内部仍按 retries 做解析重试，两层独立）；
      最坏轮数可预测，不因两类失败叠加而翻倍；两类失败交替时，末次失败原因决定汇总消息。
    - 调用级失败重试（S2d）：本批 call_agent_json 抛异常（空响应 / JSONParseError /
      批级 RuntimeError 等）**只重发本批**，重试提示带「上次失败：输出为空 / 解析失败」
      帮助模型自纠；重试仍失败 → RuntimeError 汇总（含批次号 + 原因 + 已完成批次）。
      背景：单批非确定性空响应（同 prompt 复跑偶发）不再拖垮整站。
    - 失败策略（不静默降级）：
      * 单批调用失败（重试耗尽）→ RuntimeError 标注「第 k/N 批」+ 原因 + 已完成批次
      * 单批批内校验反复不合格 → RuntimeError 标注「第 k/N 批、缺失项、已完成批次」
      * NoKeyError 等用户可操作异常 → **原样上抛**，不重试也不包装（否则各站 main() 的
        NoKeyError 分支走不到，用户看不到「未配 key / 用 --demo」提示；且配置问题重试无意义）
      * merge 阶段失败 → RuntimeError 标注「merge 阶段、涉及全部 N 批」
        （merge_fn 合并全部批次后才发现问题，无法再定位到单个批次）
    """
    if not batches:
        raise RuntimeError(f"{agent} 分批调用失败：批次列表为空")
    total = len(batches)
    batch_retries = max(0, batch_retries)  # 防负数：至少尝试 1 次，避免空转 append(None)
    counter = count_fn or _count_batch_items
    results: list[Any] = []
    for idx, user_prompt in enumerate(batches, start=1):
        # 批内循环：调用级失败 / 校验不合格都只重发本批，共用 batch_retries 预算
        attempt_prompt = user_prompt
        result: Any = None
        last_verr: str | None = None      # 校验不合格原因（重试耗尽时汇总用）
        last_call_exc: Exception | None = None  # 调用级失败异常（重试耗尽时汇总用）
        for attempt in range(batch_retries + 1):
            # 1) 本批调用：NoKeyError 原样上抛；其它异常纳入重试（S2d）
            try:
                result = call_agent_json(caller, agent, soul_name, attempt_prompt, retries=retries)
            except NoKeyError:
                # 用户可操作异常（未配 DEEPSEEK_API_KEY）：原样上抛 → 各站 main() 的
                # NoKeyError 分支给出「配置 key 或改用 --demo」的提示（ocr medium 修复）
                raise
            except Exception as exc:
                last_call_exc = exc
                last_verr = None
                if attempt >= batch_retries:
                    break  # 重试预算耗尽 → 循环外统一汇总（含批次号 + 原因）
                hint = batch_failure_hint(exc)
                print(f"[批次 {idx}/{total}] 调用失败（{hint}），重试 {attempt + 1}/{batch_retries}")
                attempt_prompt = _batch_retry_prompt(user_prompt, f"上次失败：{hint}")
                continue
            last_call_exc = None
            # 2) 批内校验：不合格同样只重发本批（共用同一重试预算）
            if batch_validator is None:
                last_verr = None
                break
            try:  # validator 自身异常也要保留批次定位（ocr medium 修复）
                verr = batch_validator(result, idx)
            except Exception as exc:
                done = "、".join(f"第 {i} 批" for i in range(1, idx)) or "无"
                raise RuntimeError(
                    f"{agent} 第 {idx}/{total} 批校验器异常（已完成批次：{done}）：{exc}"
                ) from exc
            if verr is None:
                last_verr = None
                break
            last_verr = verr
            if attempt < batch_retries:
                print(f"[批次 {idx}/{total}] 校验未过（{verr}），重试 {attempt + 1}/{batch_retries}")
                attempt_prompt = _batch_retry_prompt(
                    user_prompt, f"上次输出不合格：{verr}。请补全缺失项"
                )
        if last_call_exc is not None:
            # 调用级失败重试耗尽：汇总报错（含批次号 + 原因 + 已完成批次），不静默产出
            done = "、".join(f"第 {i} 批" for i in range(1, idx)) or "无"
            raise RuntimeError(
                f"{agent} 第 {idx}/{total} 批失败（重试 {batch_retries} 次仍失败："
                f"{batch_failure_hint(last_call_exc)}；已完成批次：{done}；"
                f"已成功 {len(results)} 批）：{last_call_exc}"
            ) from last_call_exc
        if last_verr is not None:
            # 批内校验反复不合格：汇总报错（含批次号 + 缺失项 + 已完成批次），不静默产出
            done = "、".join(f"第 {i} 批" for i in range(1, idx)) or "无"
            raise RuntimeError(
                f"{agent} 第 {idx}/{total} 批校验未通过（重试 {batch_retries} 次仍不合格："
                f"{last_verr}；已完成批次：{done}）"
            )
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
