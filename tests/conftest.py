"""pytest 共享配置：把仓库根目录加入 sys.path，使顶层 schemas/ 与 studios/ 可导入。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
