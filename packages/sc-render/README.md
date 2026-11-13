# sc-render

ComfyUI + LTX-Video 2B 出片客户端（纯标准库，零第三方依赖）。M0 抽包：由主仓
`scripts/comfyui_video.py` 原样搬迁为 `sc_render.comfyui`，workflow/显存纪律/失败分类未改动。

- `build_ltxv_workflow(...)`：构造已验过的 LTXV 2B workflow
- `submit` / `wait_and_download`：提交 → 轮询 → 落盘（本地 copy 优先，缺失走 `/view`）
- `unload_ollama()` / `gpu_mb()` / `last_run()`：渲染前卸 ollama、峰值显存采样
- `render_clip(prompt, out_dir, ...)`：一站式出片，返回产物路径

## 最小用法

```python
from sc_render import render_clip

files = render_clip("雨夜便利店，中景缓慢推近", "./out")
print(files[0])
```

已验参数（12GB 卡）：1024×576 · 49 帧 · 30 步 · cfg 3.0 · fps 25 ≈ 55s/镜。
