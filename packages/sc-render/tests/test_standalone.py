"""脱离主仓 smoke 测试：干净子进程里只从本包 src 导入并构造 workflow。

判定「独立可用」：
1. cwd 在临时目录（不依赖仓库根）；
2. 清空 PYTHONPATH，并把仓库根从子进程 sys.path 移除（不隐式 import 主仓）；
3. 只显式加入本包 `src/`，import 后断言来源路径，且主仓 `studios/` / `schemas/` 未被加载。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
PKG_SRC = PKG_ROOT / "src"
REPO_ROOT = PKG_ROOT.parents[1]

_SCRIPT = f"""
import os, sys
_REPO_ROOT = {str(REPO_ROOT)!r}
_PKG_SRC = {str(PKG_SRC)!r}
# 只屏蔽主仓源码目录（保留 .venv/site-packages，第三方依赖仍需可见）
_blocked = tuple(os.path.join(_REPO_ROOT, d)
                 for d in ('studios', 'schemas', 'tests', 'scripts', 'packages'))
sys.path = [p for p in sys.path
            if p and os.path.abspath(p) != _REPO_ROOT
            and not os.path.abspath(p).startswith(_blocked)]
sys.path.insert(0, _PKG_SRC)

os.environ["SCENE_COMFY_OUTPUT"] = "/tmp/sc-render-standalone-output"
import sc_render
from sc_render import comfyui
assert os.path.realpath(sc_render.__file__).startswith(os.path.realpath(_PKG_SRC)), sc_render.__file__

wf = sc_render.build_ltxv_workflow(
    "雨夜便利店，中景缓慢推近", "blurry", 1024, 576, 49, 30, 3.0, 42, 25.0,
    "ltx-video-2b-v0.9.5.safetensors",
)
assert wf["11"]["class_type"] == "SaveWEBM", wf["11"]
assert wf["9"]["class_type"] == "SamplerCustom", wf["9"]
# 产物目录可由环境变量覆盖（不再写死某台机器的用户名）
assert comfyui.DEFAULT_COMFY_OUTPUT == "/tmp/sc-render-standalone-output", comfyui.DEFAULT_COMFY_OUTPUT
assert comfyui._default_comfy_output() == "/tmp/sc-render-standalone-output"

assert 'studios' not in sys.modules, '不应加载主仓 studios'
assert 'schemas' not in sys.modules, '不应加载主仓 schemas'
print('OK', sc_render.__file__)
"""


def test_import_and_run_without_main_repo(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    proc = subprocess.run([sys.executable, "-c", _SCRIPT], cwd=tmp_path, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert proc.stdout.startswith("OK ")
