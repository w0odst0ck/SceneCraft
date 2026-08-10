"""把 artifacts/human1 的 script.json 血缘标记改为 human（模拟人工修改）。"""
import json
import sys
from pathlib import Path

project = sys.argv[1] if len(sys.argv) > 1 else "human1"
root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts")
p = root / project / "01_script" / "script.json"
data = json.loads(p.read_text(encoding="utf-8"))
data["edited_by"] = "human"
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("已标记 edited_by=human:", p)
