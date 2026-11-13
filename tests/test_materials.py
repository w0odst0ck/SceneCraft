"""studio_story 素材注入测试（主仓部分，§7.2 的 5 个用例）。

- demo 子进程测试走 --demo，不调真实 DeepSeek；
- 注入单测一律 stub pick_materials，不读写仓库真实 cards/（数据安全红线）。

M0 抽包：素材卡库单测（pick 用例）已迁至 packages/sc-materials/tests/test_pick.py；
文件末尾转发收集（用例只有一份，主仓 pytest 覆盖不减少）。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_studio(studio: str, project: str, artifacts_dir: Path, *extra: str,
               demo: bool = False) -> subprocess.CompletedProcess:
    """以子进程运行 studios/<studio>/run.py（demo 模式，不触发网络）；60s 超时防 hang。"""
    cmd = [sys.executable, str(ROOT / "studios" / studio / "run.py"),
           "--project", project, "--artifacts-dir", str(artifacts_dir), *extra]
    if demo:
        cmd.append("--demo")
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
                              timeout=60)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"{studio}/run.py 子进程超时（>60s）：{exc}")


def _import_run():
    import studios.studio_story.run as run_module
    return run_module


# ── §7.2 run.py 注入单测（5 个）──────────────────────

def test_run_with_material_tags_demo(tmp_path):
    """子进程 --material-tags 命中 → returncode 0，生成 01_script/script.json。"""
    project = "demo_mat"
    r = run_studio("studio_story", project, tmp_path, "--concept", "雨夜便利店的神秘顾客",
                   "--material-tags", "赛博朋克,悬疑", demo=True)
    assert r.returncode == 0, r.stderr
    script_path = tmp_path / project / "01_script" / "script.json"
    assert script_path.exists(), "story 应生成 01_script/script.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    assert script["output_hash"], "落盘时应回填 output_hash"
    manifest = json.loads((tmp_path / project / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["studios"]["script"]["status"] == "done"


def test_run_no_material_tags_backward(tmp_path):
    """E11：不传 --material-tags → returncode 0、产物结构/字段与旧版一致。"""
    project = "demo_backward"
    r = run_studio("studio_story", project, tmp_path, "--concept", "赛博快递员", demo=True)
    assert r.returncode == 0, r.stderr
    script_path = tmp_path / project / "01_script" / "script.json"
    assert script_path.exists()
    script = json.loads(script_path.read_text(encoding="utf-8"))
    assert script["output_hash"]
    manifest = json.loads((tmp_path / project / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["studios"]["script"]["status"] == "done"
    assert manifest["studios"]["script"]["output_hash"] == script["output_hash"]
    assert manifest["studios"]["script"]["cost_usd"] == 0.0  # demo 无 token 消耗
    assert manifest["current_focus"] == "script"


def test_injection_helper_pure(monkeypatch):
    """_materials_injection 纯函数：stub pick 后验证拼接逻辑（不触真实 cards/，数据安全红线）。"""
    run_module = _import_run()
    monkeypatch.setattr(
        run_module.pick_materials, "pick_materials",
        lambda tags, limit=None: "### setting: stub卡\n**可复用点**：stub 内容")
    out = run_module._materials_injection("赛博朋克")
    assert "## 参考素材（与 concept 冲突时以 concept 为准）" in out
    assert "### setting: stub卡" in out
    assert len(out) <= 2000
    assert run_module._materials_injection(None) == ""
    assert run_module._materials_injection("") == ""
    assert run_module._materials_injection("   ") == ""


def test_injection_no_match_empty(monkeypatch):
    """E9：无命中 → _materials_injection 返回空串（stub 模拟无命中，不触真实 cards/）。"""
    run_module = _import_run()
    monkeypatch.setattr(run_module.pick_materials, "pick_materials",
                        lambda tags, limit=None: "")
    assert run_module._materials_injection("不存在的标签XYZ") == ""


def test_injection_module_missing(monkeypatch):
    """E10：pick_materials 缺失 → _materials_injection 抛 RuntimeError（fail-closed）。"""
    run_module = _import_run()
    monkeypatch.setattr(run_module, "pick_materials", None)
    with pytest.raises(RuntimeError, match="fail-closed"):
        run_module._materials_injection("赛博朋克")


# ── M0 抽包：转发包内 pick 用例（用例只有一份，主仓 pytest 覆盖不减少）──
from _pkg_test_loader import load_tests  # noqa: E402

load_tests("sc-materials", "test_pick.py")
