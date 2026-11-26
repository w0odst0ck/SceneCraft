"""ai-short-drama 测试共享配置：把子项目根加入 sys.path。

⚠ 本目录必须用独立 pytest 进程运行（不要与仓库顶层 tests/ 同进程），
否则 ai-short-drama/schemas 与顶层 schemas/ 同名包会在 sys.modules 冲突。
运行: cd ai-short-drama && ../.venv/bin/python -m pytest tests/ -q
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
