"""端到端：临时 artifacts 目录串跑多个工作室 run.py（子进程方式，demo 模式不触发网络）。"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_studio(studio: str, project: str, artifacts_dir: Path, *extra: str,
               demo: bool = False) -> subprocess.CompletedProcess:
    """以子进程运行 studios/<studio>/run.py，返回 CompletedProcess。

    demo=True 时加 --demo（不调用 DeepSeek，走 AgentCaller 演示分支）。
    """
    cmd = [sys.executable, str(ROOT / "studios" / studio / "run.py"),
           "--project", project, "--artifacts-dir", str(artifacts_dir), *extra]
    if demo:
        cmd.append("--demo")
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)


def test_story_then_art(tmp_path):
    """串跑 story → art：产物文件生成、manifest 更新、血缘记录上游 hash。"""
    project = "demo1"

    # 1) Studio Story
    r1 = run_studio("studio_story", project, tmp_path, "--concept", "赛博快递员", demo=True)
    assert r1.returncode == 0, r1.stderr
    script_path = tmp_path / project / "01_script" / "script.json"
    assert script_path.exists(), "story 应生成 01_script/script.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    assert script["output_hash"], "落盘时应回填 output_hash"

    manifest_path = tmp_path / project / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["studios"]["script"]["status"] == "done"
    assert manifest["studios"]["script"]["output_hash"] == script["output_hash"]
    assert manifest["studios"]["script"]["cost_usd"] == 0.0  # demo 无 token 消耗
    assert manifest["current_focus"] == "script"

    # 2) Studio Art 消费 story 产物
    r2 = run_studio("studio_art", project, tmp_path, demo=True)
    assert r2.returncode == 0, r2.stderr
    art_path = tmp_path / project / "02_art" / "visual_bible.json"
    assert art_path.exists(), "art 应生成 02_art/visual_bible.json"

    manifest2 = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest2["studios"]["art"]["status"] == "done"
    # 血缘：art 记录了上游 script 的 hash
    assert manifest2["studios"]["art"]["upstream_hash"]["script"] == script["output_hash"]


def test_missing_input_friendly_error(tmp_path):
    """缺上游产物时友好报错：返回码非 0，stderr 提示先运行上游工作室。"""
    project = "demo2"
    r = run_studio("studio_art", project, tmp_path)  # 未先跑 Studio Story
    assert r.returncode != 0
    assert "缺少输入产物" in r.stderr
    assert "上游" in r.stderr


def test_all_studios_chain(tmp_path):
    """全链串跑 story → art → shoot → prompt → edit → render → qc，全部成功。"""
    project = "demo3"
    chain = ["studio_story", "studio_art", "studio_shoot", "studio_prompt",
             "studio_edit", "studio_render", "studio_qc"]
    for studio in chain:
        extra = ("--concept", "赛博快递员") if studio == "studio_story" else ()
        r = run_studio(studio, project, tmp_path, *extra, demo=True)
        assert r.returncode == 0, f"{studio} 失败：{r.stderr}\n{r.stdout}"

    # 7 个 stage 目录 + manifest 齐备
    expected = ["01_script", "02_art", "03_shoot", "04_prompt", "05_edit", "06_render", "07_qc"]
    for stage in expected:
        assert (tmp_path / project / stage).is_dir(), f"缺少 stage 目录 {stage}"

    # render 站输出 render_plan.json（降级实现产物）
    assert (tmp_path / project / "06_render" / "render_plan.json").exists()
    assert (tmp_path / project / "07_qc" / "qc_report.json").exists()

    manifest = json.loads((tmp_path / project / "manifest.json").read_text(encoding="utf-8"))
    for key in ["script", "art", "shoot", "prompt", "edit", "render", "qc"]:
        assert manifest["studios"][key]["status"] == "done", f"{key} 未 done"
        assert manifest["studios"][key]["output_hash"], f"{key} 缺少 output_hash"
        assert manifest["studios"][key]["cost_usd"] is not None, f"{key} 缺少 cost_usd"
    assert manifest["current_focus"] == "qc"
