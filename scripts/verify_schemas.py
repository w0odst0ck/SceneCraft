"""验证新增契约:demo 实例化 + round-trip + computed_field。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.qc_report import QcReport, QcFinding
from schemas.render_plan import RenderPlan

r = QcReport.demo()
assert r.passed is True
assert r.total_score >= 60
data = r.model_dump(mode="json")
assert data["passed"] is True, "computed_field 应出现在序列化输出中"
r2 = QcReport.model_validate(data)
assert r2 == r
low = QcReport(stage="script", total_score=30.0)
assert low.passed is False

rp = RenderPlan.demo()
assert rp.total_estimated_cost_usd >= 0
data2 = rp.model_dump(mode="json")
assert RenderPlan.model_validate(data2) == rp
assert data2["shots"][0]["provider"] == "openmontage-pending"

print("OK: QcReport / RenderPlan 契约验证通过")
