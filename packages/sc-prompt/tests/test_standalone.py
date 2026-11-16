"""脱离主仓 smoke 测试：干净子进程里只从本包（+依赖 sc-batching）src 导入并合并批次。

判定「独立可用」：
1. cwd 在临时目录（不依赖仓库根）；
2. 清空 PYTHONPATH，并把仓库根从子进程 sys.path 移除（不隐式 import 主仓）；
3. 只显式加入本包与依赖包 `src/`，import 后断言来源路径，且主仓 `studios/` / `schemas/` 未被加载。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
PKG_SRC = PKG_ROOT / "src"
REPO_ROOT = PKG_ROOT.parents[1]
BATCHING_SRC = REPO_ROOT / "packages" / "sc-batching" / "src"

_SCRIPT = f"""
import os, sys
_REPO_ROOT = {str(REPO_ROOT)!r}
_PKG_SRC = {str(PKG_SRC)!r}
_BATCHING_SRC = {str(BATCHING_SRC)!r}
# 只屏蔽主仓源码目录（保留 .venv/site-packages，第三方依赖仍需可见）
_blocked = tuple(os.path.join(_REPO_ROOT, d)
                 for d in ('studios', 'schemas', 'tests', 'scripts', 'packages'))
sys.path = [p for p in sys.path
            if p and os.path.abspath(p) != _REPO_ROOT
            and not os.path.abspath(p).startswith(_blocked)]
sys.path.insert(0, _BATCHING_SRC)
sys.path.insert(0, _PKG_SRC)

import sc_prompt
assert os.path.realpath(sc_prompt.__file__).startswith(os.path.realpath(_PKG_SRC)), sc_prompt.__file__

merged = sc_prompt.merge_prompt_lists(
    [
        {{"model": "Kling 2.0", "aspect_ratio": "16:9",
         "prompts": {{"SHOT_1": {{"shot_id": "SHOT_1", "prompt": "雨夜便利店，中景缓慢推近"}}}}}},
        {{"prompts": {{"SHOT_2": {{"shot_id": "SHOT_2", "prompt": "雨幕中的霓虹街角"}}}}}},
    ],
    default_model="Kling 2.0",
    default_aspect_ratio="16:9",
)
assert merged["model"] == "Kling 2.0", merged
assert merged["aspect_ratio"] == "16:9", merged
assert set(merged["prompts"]) == {{"SHOT_1", "SHOT_2"}}, merged

assert 'studios' not in sys.modules, '不应加载主仓 studios'
assert 'schemas' not in sys.modules, '不应加载主仓 schemas'
print('OK', sc_prompt.__file__)
"""


def test_import_and_run_without_main_repo(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    proc = subprocess.run([sys.executable, "-c", _SCRIPT], cwd=tmp_path, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert proc.stdout.startswith("OK ")
