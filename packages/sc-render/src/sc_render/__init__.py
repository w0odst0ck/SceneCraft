"""sc_render — ComfyUI LTX-Video 渲染客户端（纯标准库，零第三方依赖）

M0 抽包：由 SceneCraft 仓库 `scripts/comfyui_video.py` 原样搬迁为 `sc_render.comfyui`，
逻辑未改动（workflow 构造 / 提交轮询 / 显存纪律 / 失败分类）。
主仓 `scripts/comfyui_video.py` 保留为模块别名转发层，旧 import 与 CLI 继续有效。

最小用法：
    from sc_render import render_clip, ComfyUILTX  # 见下
    files = render_clip(prompt, out_dir)           # 卸 ollama → 出片 → 返回产物路径

说明：M0 只搬不改，尚未提供方案里的 ComfyUILTX 类；先用函数式 API：
    build_ltxv_workflow / submit / wait_and_download / render_clip。
"""
from sc_render.comfyui import (
    DEFAULT_BASE_URL,
    DEFAULT_CFG,
    DEFAULT_CKPT,
    DEFAULT_COMFY_OUTPUT,
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_LENGTH,
    DEFAULT_MAX_WAIT,
    DEFAULT_NEGATIVE,
    DEFAULT_POLL,
    DEFAULT_SEED,
    DEFAULT_STEPS,
    DEFAULT_WIDTH,
    TEXT_ENCODER,
    build_ltxv_workflow,
    gpu_mb,
    interrupt,
    last_run,
    main,
    render_clip,
    submit,
    unload_ollama,
    wait_and_download,
)

__all__ = [
    "build_ltxv_workflow",
    "submit",
    "wait_and_download",
    "interrupt",
    "render_clip",
    "unload_ollama",
    "gpu_mb",
    "last_run",
    "main",
    "DEFAULT_BASE_URL",
    "DEFAULT_COMFY_OUTPUT",
    "DEFAULT_CKPT",
    "TEXT_ENCODER",
    "DEFAULT_NEGATIVE",
    "DEFAULT_WIDTH",
    "DEFAULT_HEIGHT",
    "DEFAULT_LENGTH",
    "DEFAULT_STEPS",
    "DEFAULT_CFG",
    "DEFAULT_SEED",
    "DEFAULT_FPS",
    "DEFAULT_POLL",
    "DEFAULT_MAX_WAIT",
]
