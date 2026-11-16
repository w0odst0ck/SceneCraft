"""脱离主仓 smoke 测试：干净子进程里只从本包 src 导入并跑一次最小分批工具调用。

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

import sc_batching
assert os.path.realpath(sc_batching.__file__).startswith(os.path.realpath(_PKG_SRC)), sc_batching.__file__

data = sc_batching.safe_parse_json('```json\\n{{"timeline": [1, 2, 3]}}\\n```')
assert data == {{"timeline": [1, 2, 3]}}, data
assert sc_batching.count_batch_key(data, "timeline") == 3
assert sc_batching.as_dict([1, 2]) == {{}}   # dict-safe：顶层 list 不炸

assert 'studios' not in sys.modules, '不应加载主仓 studios'
assert 'schemas' not in sys.modules, '不应加载主仓 schemas'
print('OK', sc_batching.__file__)
"""


def test_import_and_run_without_main_repo(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    proc = subprocess.run([sys.executable, "-c", _SCRIPT], cwd=tmp_path, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert proc.stdout.startswith("OK ")
