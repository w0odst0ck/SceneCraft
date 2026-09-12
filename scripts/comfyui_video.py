#!/usr/bin/env python3
"""ComfyUI LTX-Video 2B 渲染客户端（纯标准库，零第三方依赖）。

从已验证 spike（tmp/spike_ltxv.py，跑通 3 次含真实六要素 prompt）提炼：
    构造 LTXV workflow → POST /prompt → 轮询 /history → 从 ComfyUI output 目录 copy 产物

显存纪律（12GB 卡须独占 GPU）：
- 渲染前 unload_ollama() 卸载 ollama 已加载模型，腾出显存给 ComfyUI；
- 轮询期间采样 nvidia-smi，记录峰值显存与耗时（模块级 _LAST_RUN，经 last_run() 读取）。

调用方：
- studios/studio_render/run.py（--render：逐镜串行真实出片）
- 本文件 CLI（人工单独出片）：
    python scripts/comfyui_video.py "prompt 文本" --out <dir>
        [--neg ... --w 1024 --h 576 --len 49 --steps 30 --cfg 3.0 --seed 42
         --fps 25 --ckpt ltx-video-2b-v0.9.5.safetensors --max-wait 900 --base-url ...]

已验参数（LTX 2B v0.9.5）：1024x576 · 30 步 · cfg 3.0 · euler · fps 25
    → 单段约 55s，峰值显存 ~11GB（另有 t5xxl fp8 text encoder 常驻）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

# ── 端点与路径默认值（可用环境变量覆盖，便于换机器/换环境）──
DEFAULT_BASE_URL = os.environ.get("SCENE_COMFY_BASE_URL", "http://127.0.0.1:8188")
OLLAMA_BASE = os.environ.get("SCENE_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
# ComfyUI 产物落盘目录（本地 copy 源）；取不到时改用 /view API 下载（见 _download_outputs）
DEFAULT_COMFY_OUTPUT = os.environ.get("SCENE_COMFY_OUTPUT", "/home/l/opt/ComfyUI/output")

# ── 模型与默认生成参数（LTX-Video 2B v0.9.5，checkpoint 自带 VAE，另需 t5xxl encoder）──
DEFAULT_CKPT = os.environ.get("SCENE_RENDER_CKPT", "ltx-video-2b-v0.9.5.safetensors")
TEXT_ENCODER = os.environ.get("SCENE_RENDER_TEXT_ENCODER", "t5xxl_fp8_e4m3fn.safetensors")
DEFAULT_NEGATIVE = "worst quality, inconsistent motion, blurry, jittery, distorted"
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 576
DEFAULT_LENGTH = 49      # 帧数；49 帧 @fps 25 ≈ 2.0s
DEFAULT_STEPS = 30
DEFAULT_CFG = 3.0
DEFAULT_SEED = 42
DEFAULT_FPS = 25.0
DEFAULT_POLL = 5.0       # 轮询间隔（秒）
DEFAULT_MAX_WAIT = 900.0  # 单段最长等待（秒）
# SaveWEBM 文件名前缀（产物名形如 scene_render_00001.webm）
FILENAME_PREFIX = "scene_render"
# ComfyUI 产物所在的输出节点 key（不同版本/节点可能落在不同 key，逐个试）
_OUTPUT_KEYS = ("images", "video", "webm", "gifs", "gifs_video")

# 最近一次 wait_and_download 的统计：{prompt_id, duration_sec, peak_vram_mb, files}
_LAST_RUN: dict[str, Any] = {}


# ── HTTP 基础层（单测可 monkeypatch 本层函数，屏蔽真实网络）──────────

def _post_json(url: str, payload: dict, timeout: float = 120.0) -> dict:
    """POST JSON 并解析响应；HTTP/网络错误原样抛出，由上层翻译为友好报错。"""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, timeout: float = 60.0) -> dict:
    """GET 并解析 JSON 响应。"""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_bytes(url: str, timeout: float = 300.0) -> bytes:
    """GET 原始字节（/view 下载产物兜底路径用）。"""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


# ── 显存采样与 ollama 卸载 ─────────────────────────────

def _nvidia_smi_path() -> str:
    """定位 nvidia-smi（WSL 下常不在 PATH，用约定路径兜底）。"""
    return shutil.which("nvidia-smi") or "/usr/lib/wsl/lib/nvidia-smi"


def gpu_mb() -> int:
    """当前显存占用（MiB）；采样失败返回 -1（不抛异常，避免打断轮询）。"""
    try:
        proc = subprocess.run(
            [_nvidia_smi_path(), "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        return max(int(ln) for ln in lines) if lines else -1
    except Exception:
        return -1


def unload_ollama(ollama_base: str = OLLAMA_BASE) -> list[str]:
    """卸载 ollama 全部已加载模型（逐个 keep_alive=0），腾显存给 ComfyUI。

    返回被卸载的模型名列表；ollama 不可达/单个卸载失败均不抛异常（尽力而为），
    由调用方根据 gpu_mb() 自行判断显存是否腾出。
    """
    try:
        ps = _get_json(f"{ollama_base}/api/ps", timeout=10)
    except Exception as exc:  # noqa: BLE001 - 卸载是尽力而为，失败不阻塞渲染
        print(f"   （ollama /api/ps 查询失败，跳过卸载：{exc}）")
        return []
    freed: list[str] = []
    for model in ps.get("models") or []:
        if not isinstance(model, dict) or not model.get("name"):
            continue
        name = model["name"]
        try:
            _post_json(f"{ollama_base}/api/generate",
                       {"model": name, "prompt": "", "keep_alive": 0}, timeout=30)
            freed.append(name)
        except Exception:  # noqa: BLE001 - 单个模型卸载失败不影响其它
            continue
    return freed


# ── workflow 构造（LTXV 2B 文本→视频，节点连接与 spike 完全一致）────────

def build_ltxv_workflow(prompt: str, negative: str, width: int, height: int,
                        length: int, steps: int, cfg: float, seed: int,
                        fps: float, ckpt: str) -> dict:
    """构造 LTXV 2B workflow（ComfyUI /prompt 的 prompt 字段）。

    节点图（ID 与 spike 一致，已在真实 GPU 上验证）：
        1 CheckpointLoaderSimple → 2 CLIPLoader(type=ltxv) → 3/4 CLIPTextEncode
        → 5 LTXVConditioning → 9 SamplerCustom（配 6 EmptyLTXVLatentVideo /
        7 LTXVScheduler / 8 KSamplerSelect）→ 10 VAEDecode → 11 SaveWEBM
    """
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": TEXT_ENCODER, "type": "ltxv"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "5": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["3", 0], "negative": ["4", 0], "frame_rate": fps}},
        "6": {"class_type": "EmptyLTXVLatentVideo",
              "inputs": {"width": width, "height": height, "length": length, "batch_size": 1}},
        "7": {"class_type": "LTXVScheduler",
              "inputs": {"steps": steps, "max_shift": 2.05, "base_shift": 0.95,
                         "stretch": True, "terminal": 0.1, "latent": ["6", 0]}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "SamplerCustom",
              "inputs": {"model": ["1", 0], "add_noise": True, "noise_seed": seed, "cfg": cfg,
                         "positive": ["5", 0], "negative": ["5", 1], "sampler": ["8", 0],
                         "sigmas": ["7", 0], "latent_image": ["6", 0]}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {"class_type": "SaveWEBM",
               "inputs": {"images": ["10", 0], "filename_prefix": FILENAME_PREFIX,
                          "codec": "vp9", "fps": fps, "crf": 32.0}},
    }


# ── 提交 / 轮询 / 下载 ────────────────────────────────

def submit(base_url: str, workflow: dict, timeout: float = 120.0) -> str:
    """提交 workflow 到 ComfyUI，返回 prompt_id；失败抛 RuntimeError（含服务端详情）。"""
    try:
        resp = _post_json(f"{base_url}/prompt", {"prompt": workflow}, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:800]
        raise RuntimeError(f"ComfyUI 提交失败（HTTP {exc.code}）：{detail}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError(f"ComfyUI 不可达（{base_url}）：{exc}") from exc
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI 未返回 prompt_id：{resp!r}")
    return str(prompt_id)


def wait_and_download(base_url: str, prompt_id: str, out_dir: str | Path,
                      poll: float = DEFAULT_POLL, max_wait: float = DEFAULT_MAX_WAIT,
                      target_stem: str | None = None,
                      comfy_output: str | Path | None = None) -> list[Path]:
    """轮询 /history 等任务结束 → 把 ComfyUI 产物 copy 到 out_dir，返回落盘路径列表。

    - 轮询间隔 poll 秒，其间采样 nvidia-smi 记录峰值显存；超过 max_wait 抛 RuntimeError；
    - 超时会先 POST /interrupt 清掉队列里残留的任务（否则调用方重试会与新任务叠加爆显存）；
    - 任务状态非 success 抛 RuntimeError（含 ComfyUI 的 status 详情）；
    - target_stem 给定时，首个产物改名为 <target_stem><原扩展名>（render 站按 shot_id 命名）；
    - 耗时/峰值显存/产物写入模块级 _LAST_RUN（用 last_run() 读取）。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    peak = gpu_mb()  # 起点采样（可能为 -1：nvidia-smi 不可用）

    result: dict | None = None
    while result is None:
        if time.time() - t0 >= max_wait:
            interrupt(base_url, prompt_id)  # 清掉残留任务（执行中或仍在排队），避免重试叠加
            raise RuntimeError(f"渲染超时（{max_wait:.0f}s，prompt_id={prompt_id}）"
                               f"｜峰值显存 {peak} MiB")
        time.sleep(poll)
        peak = max(peak, gpu_mb())
        try:
            history = _get_json(f"{base_url}/history/{prompt_id}", timeout=30)
        except Exception:  # noqa: BLE001 - 轮询期间网络抖动不致命，下一轮再试
            continue
        if prompt_id in history:
            result = history[prompt_id]

    duration = time.time() - t0
    status = (result.get("status") or {}).get("status_str")
    _LAST_RUN.clear()
    _LAST_RUN.update({"prompt_id": prompt_id, "duration_sec": round(duration, 2),
                      "peak_vram_mb": peak, "files": []})
    if status != "success":
        detail = json.dumps(result.get("status") or {}, ensure_ascii=False)[:500]
        raise RuntimeError(f"ComfyUI 任务状态 {status}（prompt_id={prompt_id}）：{detail}")

    saved, download_errors = _download_outputs(result, out_dir, base_url, comfy_output, target_stem)
    if not saved:
        detail = f"（首个下载错误：{download_errors[0]}）" if download_errors else ""
        raise RuntimeError(f"ComfyUI 任务成功但未找到产物文件{detail}（检查 SaveWEBM 节点是否执行）")
    _LAST_RUN["files"] = [str(p) for p in saved]
    return saved


def interrupt(base_url: str = DEFAULT_BASE_URL, prompt_id: str | None = None,
              timeout: float = 15.0) -> bool:
    """清理 ComfyUI 上的残留任务：POST /interrupt（中断执行中的），
    并可选 POST /queue {"delete": [prompt_id]}（清掉仍在排队的同一任务）。

    渲染超时后调用——否则调用方重试会与残留任务同时跑两个 LTXV 任务（12GB 卡必 OOM）。
    尽力而为：只返回是否至少一个请求成功，从不抛异常（不掩盖原始错误）。
    """
    ok = False
    try:
        _post_json(f"{base_url}/interrupt", {}, timeout=timeout)
        ok = True
    except Exception:  # noqa: BLE001 - 中断仅尽力而为
        pass
    if prompt_id:
        try:
            _post_json(f"{base_url}/queue", {"delete": [prompt_id]}, timeout=timeout)
            ok = True
        except Exception:  # noqa: BLE001 - 队列清理失败不影响中断结果
            pass
    return ok


def _download_outputs(result: dict, out_dir: Path, base_url: str,
                      comfy_output: str | Path | None,
                      target_stem: str | None) -> tuple[list[Path], list[str]]:
    """从 ComfyUI 输出节点抄出产物文件到 out_dir（本地路径优先，缺失时走 /view API）。

    返回 (落盘路径列表, 错误描述列表)；单个产物失败不阻断其它，错误交给调用方并入报错信息。
    """
    root = Path(comfy_output or DEFAULT_COMFY_OUTPUT)
    saved: list[Path] = []
    errors: list[str] = []
    for node_out in (result.get("outputs") or {}).values():
        if not isinstance(node_out, dict):
            continue
        for key in _OUTPUT_KEYS:
            for item in node_out.get(key) or []:
                if not isinstance(item, dict) or not item.get("filename"):
                    continue
                name = str(item["filename"])
                subfolder = str(item.get("subfolder") or "")
                kind = str(item.get("type") or "output")  # temp 产物须带原 type，否则 /view 404
                dst = out_dir / name
                if target_stem and not saved:  # 首个产物按调用方指定名落盘
                    dst = out_dir / f"{target_stem}{Path(name).suffix or '.webm'}"
                src = root / subfolder / name
                try:
                    if src.exists():
                        shutil.copy2(src, dst)
                    else:  # ComfyUI 输出目录不可见（远程/容器）→ 走 /view 下载
                        url = (f"{base_url}/view?filename={quote(name)}"
                               f"&subfolder={quote(subfolder)}&type={quote(kind)}")
                        dst.write_bytes(_get_bytes(url))
                except Exception as exc:  # noqa: BLE001 - 单个产物失败不阻断其它
                    errors.append(f"{name}: {type(exc).__name__}: {exc}")
                    continue
                saved.append(dst)
    return saved, errors


def last_run() -> dict:
    """最近一次 wait_and_download 的统计副本（prompt_id / duration_sec / peak_vram_mb / files）。"""
    return dict(_LAST_RUN)


def render_clip(prompt: str, out_dir: str | Path, *, negative: str = DEFAULT_NEGATIVE,
                width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
                length: int = DEFAULT_LENGTH, steps: int = DEFAULT_STEPS,
                cfg: float = DEFAULT_CFG, seed: int = DEFAULT_SEED,
                fps: float = DEFAULT_FPS, ckpt: str = DEFAULT_CKPT,
                base_url: str = DEFAULT_BASE_URL, poll: float = DEFAULT_POLL,
                max_wait: float = DEFAULT_MAX_WAIT, target_stem: str | None = None,
                comfy_output: str | Path | None = None,
                unload: bool = True) -> list[Path]:
    """一站式出片：卸 ollama → 构造 workflow → 提交 → 轮询 → 下载，返回产物路径。"""
    if unload:
        freed = unload_ollama()
        print(f"显存纪律：已卸载 ollama 模型 {freed or '（无）'}｜GPU {gpu_mb()} MiB")
    workflow = build_ltxv_workflow(prompt, negative, width, height, length,
                                   steps, cfg, seed, fps, ckpt)
    prompt_id = submit(base_url, workflow)
    print(f"已提交 prompt_id={prompt_id}")
    return wait_and_download(base_url, prompt_id, out_dir, poll=poll, max_wait=max_wait,
                             target_stem=target_stem, comfy_output=comfy_output)


# ── CLI（人工单独出片）────────────────────────────────

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="comfyui_video",
        description="ComfyUI LTX-Video 2B 出片客户端（提交 workflow → 轮询 → 下载 webm）",
    )
    parser.add_argument("prompt", help="视频提示词（六要素完整文本）")
    parser.add_argument("--out", default="plan/s4-render-samples", help="产物保存目录")
    parser.add_argument("--neg", default=DEFAULT_NEGATIVE, help="负面提示词")
    parser.add_argument("--w", type=int, default=DEFAULT_WIDTH, help="宽（默认 1024）")
    parser.add_argument("--h", type=int, default=DEFAULT_HEIGHT, help="高（默认 576）")
    parser.add_argument("--len", type=int, default=DEFAULT_LENGTH, help="帧数（默认 49 ≈ 2s）")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help="采样步数（默认 30）")
    parser.add_argument("--cfg", type=float, default=DEFAULT_CFG, help="cfg（默认 3.0）")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子（默认 42）")
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS, help="帧率（默认 25）")
    parser.add_argument("--ckpt", default=DEFAULT_CKPT, help="checkpoint 名（ComfyUI checkpoints 目录内）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="ComfyUI 地址")
    parser.add_argument("--comfy-output", default=DEFAULT_COMFY_OUTPUT,
                        help="ComfyUI 产物输出目录（本地 copy 源）")
    parser.add_argument("--poll", type=float, default=DEFAULT_POLL, help="轮询间隔秒")
    parser.add_argument("--max-wait", type=float, default=DEFAULT_MAX_WAIT, help="单段最长等待秒")
    parser.add_argument("--name", default=None, help="产物文件名主干（默认用 ComfyUI 原名）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(f"=== LTX 出片：{args.w}x{args.h} · {args.len} 帧 · {args.steps} 步 · "
          f"cfg {args.cfg} · {args.ckpt} ===")
    t0 = time.time()
    try:
        files = render_clip(args.prompt, args.out, negative=args.neg, width=args.w,
                            height=args.h, length=args.len, steps=args.steps, cfg=args.cfg,
                            seed=args.seed, fps=args.fps, ckpt=args.ckpt,
                            base_url=args.base_url, poll=args.poll, max_wait=args.max_wait,
                            target_stem=args.name, comfy_output=args.comfy_output)
    except (RuntimeError, urllib.error.URLError, OSError) as exc:
        print(f"✗ 出片失败：{exc}", file=sys.stderr)
        return 1
    run = last_run()
    print(f"✓ 完成：耗时 {time.time() - t0:.1f}s｜峰值显存 {run.get('peak_vram_mb')} MiB")
    for path in files:
        size_mb = Path(path).stat().st_size / 2 ** 20
        print(f"  产物：{path}（{size_mb:.2f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
