"""检查 ai-short-drama/.env 中 DEEPSEEK_API_KEY 是否可用（不打印值）。"""
import os
from pathlib import Path

env_path = Path("ai-short-drama/.env")
if not env_path.exists():
    print("MISSING .env")
    raise SystemExit(1)

key = None
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("DEEPSEEK_API_KEY="):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
        break

print("key 已配置:", bool(key))
if key:
    print("key 是否为示例占位:", key == "sk-your-key-here")
    print("key 长度:", len(key))
