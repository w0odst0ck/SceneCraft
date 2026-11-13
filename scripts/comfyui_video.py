"""薄转发层（M0 抽包）：实现已迁至 packages/sc-render/src/sc_render/comfyui.py。

用 sys.modules 别名而非 `import *`：保证 `comfyui_video._post_json` 等
monkeypatch 与模块级状态（_LAST_RUN）与实现同源，旧调用方行为完全不变。
"""
import sys

from sc_render import comfyui as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    sys.exit(_impl.main())
