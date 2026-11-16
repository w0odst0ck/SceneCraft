# sc-render

ComfyUI + LTX-Video 2B 出片客户端（纯标准库，零第三方依赖，内建显存纪律）。
**不依赖 SceneCraft 主仓**，可独立安装使用。

## 安装

```bash
pip install -e packages/sc-render   # 仓库内可编辑安装
# 或发布后：pip install sc-render
```

## 最小用法

```python
from sc_render import render_clip

files = render_clip("雨夜便利店，中景缓慢推近", "./out")
print(files[0])
```

只构造 workflow（不联网，可用于检查/二次提交）：

```python
from sc_render import build_ltxv_workflow

workflow = build_ltxv_workflow(
    "雨夜便利店，中景缓慢推近", "blurry", 1024, 576, 49, 30, 3.0, 42, 25.0,
    "ltx-video-2b-v0.9.5.safetensors",
)
print(workflow["11"]["class_type"])   # SaveWEBM
```

## 环境变量

| 变量 | 缺省 | 说明 |
|---|---|---|
| `SCENE_COMFY_BASE_URL` | `http://127.0.0.1:8188` | ComfyUI 服务地址 |
| `SCENE_COMFY_OUTPUT` | `~/opt/ComfyUI/output`（存在时）否则 `./comfyui_output` | ComfyUI 产物目录（本地 copy 源） |
| `SCENE_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | 渲染前卸载 ollama 模型用 |
| `SCENE_RENDER_CKPT` | `ltx-video-2b-v0.9.5.safetensors` | checkpoint 名 |
| `SCENE_RENDER_TEXT_ENCODER` | `t5xxl_fp8_e4m3fn.safetensors` | 文本编码器名 |

**跨机部署**：ComfyUI 不在 `~/opt/ComfyUI/output` 时请显式设置 `SCENE_COMFY_OUTPUT`
（或调用时传 `comfy_output=`）；未设置且标准位置不存在时退化为 `<cwd>/comfyui_output`，
本地 copy 失败会改走 ComfyUI `/view` API 下载。

## 内容

- `build_ltxv_workflow(...)`：构造已验过的 LTXV 2B workflow
- `submit` / `wait_and_download`：提交 → 轮询 → 落盘（本地 copy 优先，缺失走 `/view`）
- `unload_ollama()` / `gpu_mb()` / `last_run()`：渲染前卸 ollama、峰值显存采样
- `render_clip(prompt, out_dir, ...)`：一站式出片，返回产物路径

已验参数（12GB 卡）：1024×576 · 49 帧 · 30 步 · cfg 3.0 · fps 25 ≈ 55s/镜。
