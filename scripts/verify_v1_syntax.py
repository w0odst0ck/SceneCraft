"""验收辅助脚本:验证 v1 pipeline.py 语法。"""
import ast
from pathlib import Path

src = Path("ai-short-drama/orchestration/pipeline.py").read_text(encoding="utf-8")
ast.parse(src)
print("语法 OK: ai-short-drama/orchestration/pipeline.py")
