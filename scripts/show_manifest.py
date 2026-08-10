"""打印 demo-e2e manifest 摘要（验收用）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

project = sys.argv[1] if len(sys.argv) > 1 else "demo-e2e"
root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts")
mf = json.loads((root / project / "manifest.json").read_text(encoding="utf-8"))
print(f"项目: {project}  created_at: {mf['created_at']}  current_focus: {mf['current_focus']}")
for key, st in mf["studios"].items():
    print(f"  {key:8s} status={st['status']:8s} cost_usd={st['cost_usd']} "
          f"upstream={sorted(st['upstream_hash'])} version={st['version']}")
