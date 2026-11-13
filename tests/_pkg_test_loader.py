"""M0 抽包辅助：把 packages/*/tests 下的测试模块转发到主仓测试命名空间。

背景：M0 要求「测试迁入各包」且「主仓 `pytest tests/` 仍是 140 passed」。
用例只保留一份（包内为单一真相源），主仓保留同名薄转发文件，通过本 helper
按文件路径加载包内模块并注入 `test_*` 函数（函数对象、mark、参数化均原样保留）。

非测试文件（不以 test_ 开头），pytest 不会收集，仅作为导入期辅助。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tests(pkg_dir: str, test_file: str) -> None:
    """加载 packages/<pkg_dir>/tests/<test_file> 并把其中 test_* 注入调用方命名空间。"""
    path = ROOT / "packages" / pkg_dir / "tests" / test_file
    mod_name = f"_m0_{pkg_dir.replace('-', '_')}_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载包内测试：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    caller_globals = sys._getframe(1).f_globals
    for name, obj in vars(module).items():
        if name.startswith("test_") and callable(obj):
            caller_globals[name] = obj
