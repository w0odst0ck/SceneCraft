#!/usr/bin/env python3
"""SceneCraft GPU 模型调度器（本地 LLM / 视频 / 图像模型串行切换）。

12GB 显存无法常驻多个本地模型，因此按 stage 串行「预热 → 校验显存 footprint」，
或整体释放，为未来生图/生视频本地后端铺路。

用法:
    python scripts/model_scheduler.py stage <stage> [--json]

    stage ∈ {llm-9b, llm-14b, video-wan, video-ltx, image, free}
      free / release : 释放 ollama 全部已加载模型（幂等，重复执行不报错）
      llm-9b/llm-14b: ollama 预热目标模型 → nvidia-smi 校验显存 ≥ 下限
      video-*/image : 本地推理后端未接入，仅预留 verify 占位（显存目标档位）

退出码: 0=成功, 1=执行失败(ollama/nvidia-smi 不可用等), 2=verify 显存不达标
依赖  : 仅 Python 标准库 + curl / nvidia-smi 子进程；零第三方 Python 包。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

# ── 服务端点 ───────────────────────────────────────────
OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_PS_URL = f"{OLLAMA_BASE}/api/ps"          # 列出已加载模型
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE}/api/generate"  # 预热/卸载模型

# ── stage → 规格表（显存下限为占位阈值，可按显卡实测调整）──
# engine: "ollama"=真实预热+verify；"reserved"=本地后端未接入，仅 verify 档位
STAGE_SPECS = {
    "llm-9b": {
        "model": "qwen3.5:9b",          # 测试环境快模型
        "engine": "ollama",
        "vram_min_mb": 5000,
    },
    "llm-14b": {
        "model": "qwen3:14b-ctx2k",     # 成品环境质量模型
        "engine": "ollama",
        "vram_min_mb": 8000,
    },
    "video-wan": {
        "model": "wan21-t2v-1.3b",      # 预留（生视频）
        "engine": "reserved",
        "vram_min_mb": 4000,
    },
    "video-ltx": {
        "model": "ltx-video",           # 预留（生视频）
        "engine": "reserved",
        "vram_min_mb": 10000,
    },
    "image": {
        "model": None,                  # 预留（生图，后端未定）
        "engine": "reserved",
        "vram_min_mb": 7000,
    },
}
# free/release 为同义词：卸载全部已加载模型
RELEASE_STAGES = ("free", "release")
STAGE_CHOICES = [*STAGE_SPECS.keys(), *RELEASE_STAGES]


class SchedulerError(RuntimeError):
    """调度执行失败（ollama/nvidia-smi 不可用、子进程报错等）。"""


# ── 子进程层（单测通过 monkeypatch _run 打桩）────────────

def _run(args: list[str]) -> subprocess.CompletedProcess:
    """执行外部命令并捕获输出；单测替换本函数即可 mock curl/nvidia-smi。"""
    return subprocess.run(args, capture_output=True, text=True, timeout=900)


def _curl_json(method: str, url: str, payload: dict | None = None,
               timeout: int = 60) -> dict:
    """curl 请求 ollama JSON API。HTTP ≥400 或网络错误 → SchedulerError。"""
    args = ["curl", "-sS", "--fail-with-body", "-m", str(timeout),
            "-X", method, url]
    if payload is not None:
        args += ["-H", "Content-Type: application/json",
                 "-d", json.dumps(payload)]
    proc = _run(args)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise SchedulerError(f"curl {method} {url} 失败 (rc={proc.returncode}): {detail}")
    body = proc.stdout.strip()
    if not body:
        return {}
    try:
        return json.loads(body)
    except ValueError as exc:
        raise SchedulerError(f"curl {method} {url} 返回非 JSON: {body[:200]!r}") from exc


# ── ollama 交互 ───────────────────────────────────────

def list_loaded_models() -> list[str]:
    """GET /api/ps：当前加载到内存/显存的模型名列表。"""
    data = _curl_json("GET", OLLAMA_PS_URL)
    models = data.get("models", [])
    if not isinstance(models, list):
        raise SchedulerError(f"/api/ps models 字段异常（应为列表）: {models!r}")
    return [m["name"] for m in models if isinstance(m, dict) and m.get("name")]


def warmup_model(model: str) -> None:
    """预热模型：空 prompt generate + keep_alive 30m，模型常驻显存。"""
    _curl_json("POST", OLLAMA_GENERATE_URL, {
        "model": model,
        "prompt": "",
        "keep_alive": "30m",
        "stream": False,
    }, timeout=600)


def unload_model(model: str) -> None:
    """卸载单个模型（keep_alive=0 立即释放）。"""
    _curl_json("POST", OLLAMA_GENERATE_URL, {"model": model, "keep_alive": 0})


# ── nvidia-smi 显存 ───────────────────────────────────

def vram_used_mb() -> int:
    """读 nvidia-smi memory.used（MB）。多 GPU 取最大占用值。"""
    import shutil
    smi = shutil.which("nvidia-smi") or "/usr/lib/wsl/lib/nvidia-smi"
    proc = _run([smi, "--query-gpu=memory.used",
                 "--format=csv,noheader,nounits"])
    if proc.returncode != 0:
        raise SchedulerError(f"nvidia-smi 失败 (rc={proc.returncode}): {(proc.stderr or '').strip()}")
    try:
        values = [int(line.strip()) for line in proc.stdout.splitlines()
                  if line.strip()]
    except ValueError:
        raise SchedulerError(f"nvidia-smi 输出无法解析: {proc.stdout.strip()!r}")
    if not values:
        raise SchedulerError("nvidia-smi 未返回任何 GPU")
    return max(values)


# ── stage 执行 ───────────────────────────────────────

def run_stage(stage: str, verbose: bool = False) -> dict:
    """执行一个 stage，返回 {stage, model, released, vram_mb, ok}。

    ok=False 表示 verify 显存不达标（调用方按 exit 2 退出）。
    """
    if stage in RELEASE_STAGES:
        return _run_release(stage, verbose=verbose)

    spec = STAGE_SPECS[stage]
    model = spec["model"]
    if spec["engine"] == "ollama":
        if verbose:
            print(f"⏳ 预热 {model}（keep_alive 30m）…")
        warmup_model(model)
    else:
        if verbose:
            print(f"⚠ stage {stage} 为预留占位（本地推理后端未接入），"
                  f"跳过 ollama 预热，仅 verify 显存档位 ≥{spec['vram_min_mb']}MB")
    vram = vram_used_mb()
    ok = vram >= spec["vram_min_mb"]
    if verbose:
        mark = "✅" if ok else "✗"
        print(f"{mark} verify: 显存 {vram}MB {'≥' if ok else '<'} 下限 {spec['vram_min_mb']}MB")
    return {"stage": stage, "model": model, "released": [],
            "vram_mb": vram, "ok": ok}


def _run_release(stage: str, verbose: bool = False) -> dict:
    """释放全部已加载模型；无已加载模型时同样成功（幂等）。"""
    loaded = list_loaded_models()
    released: list[str] = []
    for name in loaded:
        if verbose:
            print(f"⏏ 卸载 {name} …")
        unload_model(name)
        released.append(name)
    if verbose:
        print(f"已释放 {len(released)} 个模型: {released or '(无)'}")
    # nvidia-smi 仅作报告；不可用（如纯 CPU）不影响释放成功
    try:
        vram = vram_used_mb()
    except SchedulerError:
        vram = None
    return {"stage": stage, "model": None, "released": released,
            "vram_mb": vram, "ok": True}


def _stage_model(stage: str) -> str | None:
    """错误报告用：stage 对应的目标模型名（free/release 无）。"""
    if stage in RELEASE_STAGES:
        return None
    return STAGE_SPECS[stage]["model"]


# ── CLI ──────────────────────────────────────────────

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="model_scheduler",
        description="SceneCraft GPU 模型调度器：串行预热/释放本地模型并校验显存",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_stage = sub.add_parser(
        "stage",
        help=f"执行调度 stage: {', '.join(STAGE_CHOICES)}",
    )
    p_stage.add_argument("stage", choices=STAGE_CHOICES,
                         help="free/release=卸载全部已加载模型；"
                              "其余=预热目标模型并 verify 显存")
    p_stage.add_argument("--json", action="store_true",
                         help="输出 JSON: {stage, model, released, vram_mb, ok}")
    return parser.parse_args(argv)


def _print_summary(result: dict, exit_code: int) -> None:
    stage = result["stage"]
    if stage in RELEASE_STAGES:
        n = len(result["released"])
        tail = "" if result["vram_mb"] is None else f"，当前显存 {result['vram_mb']}MB"
        if n:
            print(f"✅ {stage}: 已释放 {n} 个模型 {result['released']}{tail}")
        else:
            print(f"✅ {stage}: 没有已加载模型，无需释放（幂等）{tail}")
        return
    model = result["model"] or "(预留，无模型)"
    if exit_code == 0:
        print(f"✅ {stage} 就绪：模型={model}，显存 {result['vram_mb']}MB "
              f"≥ 下限 {STAGE_SPECS[stage]['vram_min_mb']}MB")
    else:
        print(f"✗ {stage} 显存 {result['vram_mb']}MB "
              f"< 下限 {STAGE_SPECS[stage]['vram_min_mb']}MB（exit 2）")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    verbose = not args.json
    try:
        result = run_stage(args.stage, verbose=verbose)
    except SchedulerError as exc:
        if verbose:
            print(f"✗ 调度失败: {exc}", file=sys.stderr)
        result = {"stage": args.stage, "model": _stage_model(args.stage),
                  "released": [], "vram_mb": None, "ok": False,
                  "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        return 1
    exit_code = 0 if result["ok"] else 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        _print_summary(result, exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
