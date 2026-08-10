"""端到端测试：demo 全链（subprocess）+ mock Agent 真实链路（进程内）+ 人工产物保护。

全部不触发真实网络：demo 模式走内置演示输出；mock 模式替换 call_deepseek。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemas.editing_blueprint import EditingBlueprint
from schemas.prompt_list import PromptList
from schemas.render_plan import RenderPlan
from schemas.script import Script
from schemas.shot_list import ShotList
from schemas.visual_bible import VisualBible
from studios import agent_utils as au

# 6 类产物：相对 stage 路径 → 契约
CONTRACTS = {
    "01_script/script.json": Script,
    "02_art/visual_bible.json": VisualBible,
    "03_shoot/shot_list.json": ShotList,
    "04_prompt/prompt_list.json": PromptList,
    "05_edit/editing_blueprint.json": EditingBlueprint,
    "06_render/render_plan.json": RenderPlan,
}


def _manifest(project_dir: Path) -> dict:
    return json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))


def _run_pipeline(project: str, artifacts_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "studios" / "run_pipeline.py"),
         "--project", project, "--artifacts-dir", str(artifacts_dir), *extra],
        capture_output=True, text=True, cwd=ROOT,
    )


# ── 1) demo 模式全链（无 key 可跑）──────────────────────

def test_demo_pipeline_all_artifacts(tmp_path):
    """--demo 全链：6 类产物生成且契约校验通过、manifest 全 done、血缘链正确、cost_usd 回填。"""
    project = "demo-e2e"
    r = _run_pipeline(project, tmp_path, "--concept", "测试", "--demo")
    assert r.returncode == 0, f"全链失败：{r.stderr}\n{r.stdout}"
    pdir = tmp_path / project

    for rel, model in CONTRACTS.items():
        path = pdir / rel
        assert path.exists(), f"缺少产物 {rel}"
        inst = model.model_validate(json.loads(path.read_text(encoding="utf-8")))
        assert inst.output_hash, f"{rel} 未回填 output_hash"
        assert "TODO_PHASE_B" not in path.read_text(encoding="utf-8"), f"{rel} 仍有占位"

    mf = _manifest(pdir)
    for key in ["script", "art", "shoot", "prompt", "edit", "render"]:
        st = mf["studios"][key]
        assert st["status"] == "done", f"{key} 未 done"
        assert st["cost_usd"] is not None and st["cost_usd"] >= 0, f"{key} cost_usd 未回填"

    # 血缘链：art←script；shoot←script+art；prompt←shoot+art；edit←shoot+script；render←prompt+edit
    edges = {
        "art": ["script"],
        "shoot": ["script", "art"],
        "prompt": ["shoot", "art"],
        "edit": ["shoot", "script"],
        "render": ["prompt", "edit"],
    }
    for key, ups in edges.items():
        uh = mf["studios"][key]["upstream_hash"]
        for up in ups:
            assert uh.get(up) == mf["studios"][up]["output_hash"], f"{key}←{up} 血缘 hash 不一致"


# ── 2) mock Agent 真实链路（进程内，替换 call_deepseek）──

def _detect_agent(system: str) -> str:
    """从 system prompt（SOUL 首行标题）反推 Agent 名，供 mock 返回对应演示输出。"""
    for agent, tag in [
        ("producer", "# Producer"), ("writer", "# Writer"), ("director", "# Director"),
        ("art_director", "# Art Director"), ("cinematographer", "# Cinematographer"),
        ("actor", "# Actor"), ("prompter", "# Prompter"), ("editor", "# Editor"),
        ("critic", "# Critic"),
    ]:
        if tag in system:
            return agent
    raise AssertionError(f"无法识别 Agent：{system[:60]!r}")


def test_mocked_pipeline_lineage_and_cost(tmp_path, monkeypatch):
    """mock 所有 Agent 调用（demo 生成 + 固定 usage）→ 全链跑通 → 血缘链 + cost_usd 精确回填。"""
    calls = {"n": 0}

    def fake_call_deepseek(system, user, model=None):
        calls["n"] += 1
        agent = _detect_agent(system)
        return au.demo_output(agent, user), {"prompt_tokens": 100, "completion_tokens": 50}

    monkeypatch.setattr(au, "call_deepseek", fake_call_deepseek)

    project = "mock1"
    pdir = tmp_path / project
    common_args = ["--project", project, "--artifacts-dir", str(tmp_path)]

    from studios.studio_story import run as story
    from studios.studio_art import run as art
    from studios.studio_shoot import run as shoot
    from studios.studio_prompt import run as prompt
    from studios.studio_edit import run as edit
    from studios.studio_render import run as render

    assert story.main([*common_args, "--concept", "雨夜便利店的神秘顾客"]) == 0
    assert art.main(common_args) == 0
    assert shoot.main(common_args) == 0
    assert prompt.main(common_args) == 0
    assert edit.main(common_args) == 0
    assert render.main(common_args) == 0

    # 6 类产物齐全
    for rel, model in CONTRACTS.items():
        assert model.model_validate(json.loads((pdir / rel).read_text(encoding="utf-8")))
    mf = _manifest(pdir)
    for key in ["script", "art", "shoot", "prompt", "edit", "render"]:
        assert mf["studios"][key]["status"] == "done"

    # 血缘链正确
    assert mf["studios"]["art"]["upstream_hash"]["script"] == mf["studios"]["script"]["output_hash"]
    assert mf["studios"]["shoot"]["upstream_hash"]["art"] == mf["studios"]["art"]["output_hash"]
    assert mf["studios"]["render"]["upstream_hash"]["prompt"] == mf["studios"]["prompt"]["output_hash"]
    assert mf["studios"]["render"]["upstream_hash"]["edit"] == mf["studios"]["edit"]["output_hash"]

    # cost_usd：mock 每次调用 usage=100/50 tokens
    # 单次成本 = 100/1000*0.0014 + 50/1000*0.0028 = 0.00028
    per_call = 100 / 1000 * au.PRICE_INPUT_PER_1K + 50 / 1000 * au.PRICE_OUTPUT_PER_1K
    expected = {"script": 2 * per_call, "art": per_call, "shoot": 3 * per_call,
                "prompt": per_call, "edit": per_call, "render": 0.0}
    for key, exp in expected.items():
        assert mf["studios"][key]["cost_usd"] == pytest.approx(exp, abs=1e-9), f"{key} cost_usd 错误"
    assert calls["n"] == 8  # producer/writer + art_director + director/cinematographer/actor + prompter + editor


# ── 3) 人工产物保护（血缘保护最简版）────────────────────

def test_human_edit_protection(tmp_path):
    """产物 edited_by=human 后重跑该站 → 拒绝覆盖并报错，文件保持原样。"""
    project = "human1"
    r1 = _run_pipeline(project, tmp_path, "--concept", "测试", "--demo", "--from", "script")
    assert r1.returncode == 0, r1.stderr
    script_path = tmp_path / project / "01_script" / "script.json"

    # 模拟人工修改：仅把血缘标记改为 human（内容不动，便于比对）
    data = json.loads(script_path.read_text(encoding="utf-8"))
    data["edited_by"] = "human"
    human_version = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    script_path.write_text(human_version, encoding="utf-8")

    r2 = subprocess.run(
        [sys.executable, str(ROOT / "studios" / "studio_story" / "run.py"),
         "--project", project, "--artifacts-dir", str(tmp_path), "--concept", "测试", "--demo"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r2.returncode != 0, "应拒绝覆盖人工修改"
    assert "人工修改" in r2.stderr
    # 人工版本必须原样保留（未被 AI 重新生成覆盖）
    assert script_path.read_text(encoding="utf-8") == human_version, "人工修改的产物被覆盖了"


# ── 4) 无 key 且非 demo → 友好报错（NoKeyError）──────────

def test_no_key_non_demo_raises(tmp_path, monkeypatch):
    """无 key 且未指定 --demo：真实模式抛 NoKeyError（由 run.py 决定 demo 或报错）。"""
    monkeypatch.setattr(au, "get_api_key", lambda: None)
    from studios.studio_story import run as story
    with pytest.raises(au.NoKeyError):
        story.main(["--project", "nokey1", "--artifacts-dir", str(tmp_path), "--concept", "测试"])
