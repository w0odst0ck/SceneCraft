"""验证 demo-e2e 全链产物:6 类产物契约校验 + manifest 血缘链 + cost_usd。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.script import Script
from schemas.visual_bible import VisualBible
from schemas.shot_list import ShotList
from schemas.prompt_list import PromptList
from schemas.editing_blueprint import EditingBlueprint
from schemas.render_plan import RenderPlan

PROJECT = Path("artifacts/demo-e2e")

# 1) 6 类产物存在 + 契约校验
contracts = {
    "01_script/script.json": Script,
    "02_art/visual_bible.json": VisualBible,
    "03_shoot/shot_list.json": ShotList,
    "04_prompt/prompt_list.json": PromptList,
    "05_edit/editing_blueprint.json": EditingBlueprint,
    "06_render/render_plan.json": RenderPlan,
}
for rel, model in contracts.items():
    path = PROJECT / rel
    assert path.exists(), f"缺少产物 {path}"
    inst = model.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert inst.output_hash, f"{rel} 未回填 output_hash"
    assert "TODO_PHASE_B" not in path.read_text(encoding="utf-8"), f"{rel} 仍有占位"
print("✅ 6 类产物全部生成、契约校验通过、无 TODO 占位")

# 2) manifest 血缘链 + cost_usd
manifest = json.loads((PROJECT / "manifest.json").read_text(encoding="utf-8"))
for key in ["script", "art", "shoot", "prompt", "edit", "render"]:
    st = manifest["studios"][key]
    assert st["status"] == "done", f"{key} 未 done"
    assert st["output_hash"], f"{key} 缺 output_hash"
    assert st["cost_usd"] is not None and st["cost_usd"] >= 0, f"{key} cost_usd 未回填"
print("✅ manifest 各站 done + cost_usd 已回填")

# 血缘链:art←script; shoot←script+art; prompt←shoot+art; edit←shoot+script; render←prompt+edit
edges = {
    "art": ["script"],
    "shoot": ["script", "art"],
    "prompt": ["shoot", "art"],
    "edit": ["shoot", "script"],
    "render": ["prompt", "edit"],
}
for key, ups in edges.items():
    uh = manifest["studios"][key]["upstream_hash"]
    for up in ups:
        assert up in uh, f"{key} 血缘缺 {up}"
        assert uh[up] == manifest["studios"][up]["output_hash"], f"{key}←{up} hash 不一致"
print("✅ 血缘链正确（各站 upstream_hash 与上游 output_hash 一致）")

# 3) render 计划内容抽查
rp = RenderPlan.model_validate(json.loads((PROJECT / "06_render/render_plan.json").read_text(encoding="utf-8")))
assert rp.project_id == "demo-e2e"
assert all(s.provider == "openmontage-pending" and s.status == "pending" for s in rp.shots)
assert rp.total_estimated_cost_usd > 0
assert "Phase D" in rp.notes
print(f"✅ render_plan 内容正确：{len(rp.shots)} 镜 / ${rp.total_estimated_cost_usd}")

print("\nOK: demo-e2e 全链产物验证通过")
