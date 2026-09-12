"""render 站真实渲染（--render）单测：RenderShot 扩展字段 + 成功/失败回填 + 向后兼容。

全部不触发真实渲染/网络：scripts/comfyui_video 的 submit / wait_and_download /
unload_ollama / last_run 在测试内打桩（monkeypatch render.comfyui_video 上的函数）。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.render_plan import RenderPlan, RenderShot  # noqa: E402
from studios.studio_render import run as render  # noqa: E402


@pytest.fixture(autouse=True)
def _no_unload_wait(monkeypatch):
    """真实渲染会在卸 ollama 后等 3s（显存纪律）；测试里置 0，避免拖慢用例。"""
    monkeypatch.setenv("SCENE_RENDER_UNLOAD_WAIT", "0")


# ── RenderShot 契约扩展 ──────────────────────────────

def test_render_shot_new_fields_default_none():
    """新增 4 个 optional 字段默认 None（未渲染语义），status/provider 默认值不变。"""
    shot = RenderShot(shot_id="SHOT_1", prompt="p")
    assert shot.provider == "openmontage-pending"
    assert shot.status == "pending"
    assert shot.output_file is None
    assert shot.duration_sec is None
    assert shot.peak_vram_mb is None
    assert shot.error is None


def test_render_shot_accepts_render_result_fields():
    """真实渲染结果可回填：done + comfyui-ltxv + 产物/片长/显存。"""
    shot = RenderShot(
        shot_id="SHOT_2", provider="comfyui-ltxv", prompt="p", status="done",
        output_file="proj/06_render/SHOT_2.webm", duration_sec=1.96, peak_vram_mb=11061,
    )
    assert shot.output_file.endswith("SHOT_2.webm")
    assert shot.peak_vram_mb == 11061
    assert shot.error is None

    failed = RenderShot(shot_id="SHOT_3", prompt="p", status="failed", error="RuntimeError: boom")
    assert failed.error == "RuntimeError: boom"
    assert failed.output_file is None


def test_render_plan_backward_compatible_with_legacy_json():
    """旧版 render_plan.json（无新字段）仍可校验通过，新字段读作 None。"""
    legacy = {
        "project_id": "old",
        "shots": [{"shot_id": "SHOT_1", "provider": "openmontage-pending",
                   "prompt": "p", "estimated_cost_usd": 0.01, "status": "pending"}],
        "total_estimated_cost_usd": 0.01,
    }
    plan = RenderPlan.model_validate(legacy)
    assert plan.shots[0].output_file is None
    assert plan.shots[0].duration_sec is None
    assert plan.shots[0].peak_vram_mb is None
    assert plan.shots[0].error is None
    # 序列化后新字段以 null 出现（下游读到的是显式 None，而非缺键）
    dumped = plan.model_dump(mode="json")["shots"][0]
    assert {"output_file", "duration_sec", "peak_vram_mb", "error"} <= set(dumped)


# ── 测试夹具：上游产物 + ComfyUI 打桩 ────────────────

def _write_inputs(tmp_path: Path, project: str, shot_ids: tuple[str, ...]) -> Path:
    """写 04_prompt/prompt_list.json + 05_edit/editing_blueprint.json（多镜，供 render 站消费）。"""
    pdir = tmp_path / project
    (pdir / "04_prompt").mkdir(parents=True, exist_ok=True)
    (pdir / "05_edit").mkdir(parents=True, exist_ok=True)
    prompt_list = {
        "model": "Kling 2.0",
        "aspect_ratio": "16:9",
        "prompts": {sid: {"shot_id": sid, "prompt": f"{sid} 六要素提示词"} for sid in shot_ids},
    }
    timeline = [
        {"shot_id": sid, "start_frame": i * 25, "end_frame": i * 25 + 24}
        for i, sid in enumerate(shot_ids)
    ]
    blueprint = {"target_fps": 25, "timeline": timeline,
                 "total_frames": len(shot_ids) * 25, "audio_beats": []}
    (pdir / "04_prompt" / "prompt_list.json").write_text(
        json.dumps(prompt_list, ensure_ascii=False), encoding="utf-8")
    (pdir / "05_edit" / "editing_blueprint.json").write_text(
        json.dumps(blueprint, ensure_ascii=False), encoding="utf-8")
    return pdir


def _stub_success(monkeypatch, *, peak: int = 11061, calls: list[str] | None = None) -> None:
    """打桩：卸载 ollama → 提交成功 → 写出 <shot_id>.webm 并返回统计。"""
    calls = calls if calls is not None else []
    monkeypatch.setattr(render.comfyui_video, "unload_ollama",
                        lambda *a, **kw: calls.append("unload") or ["qwen3:14b-ctx2k"])
    monkeypatch.setattr(render.comfyui_video, "gpu_mb", lambda: peak)

    def fake_submit(base_url, workflow, timeout=120.0):
        calls.append(f"submit:{workflow['3']['inputs']['text']}")
        assert workflow["1"]["inputs"]["ckpt_name"]  # workflow 带 checkpoint
        return f"pid-{workflow['3']['inputs']['text']}"

    def fake_wait(base_url, prompt_id, out_dir, poll=5.0, max_wait=900.0,
                  target_stem=None, comfy_output=None):
        calls.append(f"wait:{target_stem}")
        path = Path(out_dir) / f"{target_stem}.webm"
        path.write_bytes(b"fake-webm")
        monkeypatch.setattr(render.comfyui_video, "last_run",
                            lambda: {"prompt_id": prompt_id, "duration_sec": 55.0,
                                     "peak_vram_mb": peak, "files": [str(path)]})
        return [path]

    monkeypatch.setattr(render.comfyui_video, "submit", fake_submit)
    monkeypatch.setattr(render.comfyui_video, "wait_and_download", fake_wait)


def _read_plan(pdir: Path) -> dict:
    return json.loads((pdir / "06_render" / "render_plan.json").read_text(encoding="utf-8"))


# ── 成功路径 ─────────────────────────────────────────

def test_render_success_backfills_done_and_limit(tmp_path, monkeypatch):
    """--render --render-limit 1：SHOT_1 回填 done/comfyui-ltxv/产物/片长/峰值显存，SHOT_2 仍 pending。"""
    project = "proj-ok"
    pdir = _write_inputs(tmp_path, project, ("SHOT_1", "SHOT_2"))
    calls: list[str] = []
    _stub_success(monkeypatch, calls=calls)

    rc = render.main(["--project", project, "--artifacts-dir", str(tmp_path),
                      "--render", "--render-limit", "1"])
    assert rc == 0

    plan = _read_plan(pdir)
    shot1, shot2 = plan["shots"]
    assert shot1["status"] == "done"
    assert shot1["provider"] == "comfyui-ltxv"
    assert shot1["output_file"] == f"{project}/06_render/SHOT_1.webm"
    assert shot1["duration_sec"] == pytest.approx(49 / 25, abs=1e-3)  # 默认 49 帧 @fps 25
    assert shot1["peak_vram_mb"] == 11061
    assert shot1["error"] is None
    assert shot2["status"] == "pending" and shot2["output_file"] is None

    # 产物落盘 + 渲染前卸载 ollama（显存纪律）+ 只渲 1 镜
    assert (pdir / "06_render" / "SHOT_1.webm").exists()
    assert not (pdir / "06_render" / "SHOT_2.webm").exists()
    assert calls[0] == "unload"
    assert calls.count("unload") == 1
    assert [c for c in calls if c.startswith("submit:")] == ["submit:SHOT_1 六要素提示词"]

    # manifest：render 站 done、本地渲染成本 0
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["studios"]["render"]["status"] == "done"
    assert manifest["studios"]["render"]["cost_usd"] == 0.0


def test_render_all_shots_when_no_limit(tmp_path, monkeypatch):
    """不带 --render-limit：全部镜头都渲（每镜一次 submit）。"""
    project = "proj-all"
    pdir = _write_inputs(tmp_path, project, ("SHOT_1", "SHOT_2"))
    calls: list[str] = []
    _stub_success(monkeypatch, calls=calls)

    assert render.main(["--project", project, "--artifacts-dir", str(tmp_path),
                        "--render"]) == 0
    plan = _read_plan(pdir)
    assert [s["status"] for s in plan["shots"]] == ["done", "done"]
    assert [c for c in calls if c.startswith("submit:")] == [
        "submit:SHOT_1 六要素提示词", "submit:SHOT_2 六要素提示词"]


def test_default_without_render_flag_is_plan_only(tmp_path, monkeypatch):
    """默认（无 --render）行为不变：全 pending，且完全不触发渲染/显存卸载。"""
    project = "proj-plan"
    pdir = _write_inputs(tmp_path, project, ("SHOT_1", "SHOT_2"))
    calls: list[str] = []
    _stub_success(monkeypatch, calls=calls)

    assert render.main(["--project", project, "--artifacts-dir", str(tmp_path)]) == 0
    plan = _read_plan(pdir)
    assert [s["status"] for s in plan["shots"]] == ["pending", "pending"]
    assert {s["provider"] for s in plan["shots"]} == {"openmontage-pending"}
    assert calls == []


# ── 失败路径 ─────────────────────────────────────────

def test_render_failure_retries_then_continues(tmp_path, monkeypatch):
    """单镜失败：重试 1 次 → status=failed + error 非空，且继续下一镜不中断（返回 0）。"""
    project = "proj-fail"
    pdir = _write_inputs(tmp_path, project, ("SHOT_1", "SHOT_2"))
    attempts: list[str] = []

    def fake_submit(base_url, workflow, timeout=120.0):
        attempts.append(workflow["3"]["inputs"]["text"])
        raise RuntimeError("ComfyUI 提交失败（HTTP 500）：模型不存在")

    monkeypatch.setattr(render.comfyui_video, "unload_ollama", lambda *a, **kw: [])
    monkeypatch.setattr(render.comfyui_video, "gpu_mb", lambda: 0)
    monkeypatch.setattr(render.comfyui_video, "submit", fake_submit)
    def never(*args, **kwargs):
        pytest.fail("失败镜不应走到下载步骤")

    monkeypatch.setattr(render.comfyui_video, "wait_and_download", never)

    rc = render.main(["--project", project, "--artifacts-dir", str(tmp_path), "--render"])
    assert rc == 0  # 单镜失败不整体中止

    plan = _read_plan(pdir)
    for shot in plan["shots"]:
        assert shot["status"] == "failed"
        assert shot["error"] and "HTTP 500" in shot["error"]
        assert shot["output_file"] is None and shot["peak_vram_mb"] is None
    # 2 镜 × (首次 + 1 次重试) = 4 次尝试
    assert attempts == ["SHOT_1 六要素提示词"] * 2 + ["SHOT_2 六要素提示词"] * 2
    assert not (pdir / "06_render" / "SHOT_1.webm").exists()


def test_render_mixed_success_and_failure(tmp_path, monkeypatch):
    """首镜成功、次镜失败：互不影响，逐镜如实回填。"""
    project = "proj-mix"
    pdir = _write_inputs(tmp_path, project, ("SHOT_1", "SHOT_2"))

    def fake_submit(base_url, workflow, timeout=120.0):
        if "SHOT_2" in workflow["3"]["inputs"]["text"]:
            raise RuntimeError("ComfyUI 任务状态 error：OOM")
        return "pid-1"

    monkeypatch.setattr(render.comfyui_video, "unload_ollama", lambda *a, **kw: [])
    monkeypatch.setattr(render.comfyui_video, "gpu_mb", lambda: 11000)
    monkeypatch.setattr(render.comfyui_video, "submit", fake_submit)

    def fake_wait(base_url, prompt_id, out_dir, poll=5.0, max_wait=900.0,
                  target_stem=None, comfy_output=None):
        path = Path(out_dir) / f"{target_stem}.webm"
        path.write_bytes(b"ok")
        monkeypatch.setattr(render.comfyui_video, "last_run",
                            lambda: {"peak_vram_mb": 10999, "duration_sec": 50.0})
        return [path]

    monkeypatch.setattr(render.comfyui_video, "wait_and_download", fake_wait)

    assert render.main(["--project", project, "--artifacts-dir", str(tmp_path),
                        "--render"]) == 0
    shots = _read_plan(pdir)["shots"]
    assert shots[0]["status"] == "done" and shots[0]["peak_vram_mb"] == 10999
    assert shots[1]["status"] == "failed" and "OOM" in shots[1]["error"]


def test_render_limit_requires_render_flag_is_ignored(tmp_path, monkeypatch, capsys):
    """只给 --render-limit 不给 --render：忽略并提示（行为等价于只出计划）。"""
    project = "proj-hint"
    pdir = _write_inputs(tmp_path, project, ("SHOT_1",))
    calls: list[str] = []
    _stub_success(monkeypatch, calls=calls)

    assert render.main(["--project", project, "--artifacts-dir", str(tmp_path),
                        "--render-limit", "1"]) == 0
    assert calls == []
    assert "仅配合 --render 生效" in capsys.readouterr().out
    assert _read_plan(pdir)["shots"][0]["status"] == "pending"


def test_render_limit_must_be_positive(tmp_path):
    """--render-limit 非正数 → argparse 报错退出（不产生半成品产物）。"""
    with pytest.raises(SystemExit):
        render.main(["--project", "p", "--artifacts-dir", str(tmp_path),
                     "--render", "--render-limit", "0"])


# ── 参数来源：环境变量覆盖 ───────────────────────────

def test_render_params_env_overrides(monkeypatch):
    """SCENE_RENDER_* 环境变量可覆盖默认渲染参数（ckpt/steps/分辨率/地址等）。"""
    monkeypatch.setenv("SCENE_RENDER_CKPT", "no-such-model.safetensors")
    monkeypatch.setenv("SCENE_RENDER_STEPS", "12")
    monkeypatch.setenv("SCENE_RENDER_WIDTH", "768")
    monkeypatch.setenv("SCENE_RENDER_MAX_WAIT", "60")
    monkeypatch.setenv("SCENE_RENDER_UNLOAD_WAIT", "7.5")

    params = render.render_params()
    assert params["ckpt"] == "no-such-model.safetensors"
    assert params["steps"] == 12
    assert params["width"] == 768
    assert params["max_wait"] == 60.0
    assert params["unload_wait"] == 7.5
    assert params["height"] == render.comfyui_video.DEFAULT_HEIGHT  # 未覆盖项仍用默认


def test_render_default_params(tmp_path, monkeypatch):
    """无环境变量时用已验档默认（1024x576 / 30 步 / cfg 3.0 / fps 25 / ollama 卸载等待 3s）。"""
    for name in ("SCENE_RENDER_WIDTH", "SCENE_RENDER_HEIGHT", "SCENE_RENDER_LENGTH",
                 "SCENE_RENDER_STEPS", "SCENE_RENDER_CFG", "SCENE_RENDER_FPS",
                 "SCENE_RENDER_CKPT", "SCENE_RENDER_MAX_WAIT", "SCENE_RENDER_UNLOAD_WAIT"):
        monkeypatch.delenv(name, raising=False)

    params = render.render_params()
    assert (params["width"], params["height"], params["length"]) == (1024, 576, 49)
    assert (params["steps"], params["cfg"], params["fps"]) == (30, 3.0, 25.0)
    assert params["ckpt"] == "ltx-video-2b-v0.9.5.safetensors"
    assert params["max_wait"] == 900.0 and params["unload_wait"] == 3.0


def test_render_requires_comfyui_client(tmp_path, monkeypatch):
    """scripts/comfyui_video.py 缺失（导入失败）时 --render 明确报错，且不产出半成品。"""
    project = "proj-nomod"
    pdir = _write_inputs(tmp_path, project, ("SHOT_1",))
    monkeypatch.setattr(render, "comfyui_video", None)

    with pytest.raises(RuntimeError, match="comfyui_video.py"):
        render.main(["--project", project, "--artifacts-dir", str(tmp_path), "--render"])
    assert not (pdir / "06_render" / "render_plan.json").exists()


def test_render_uses_env_ckpt_in_workflow(tmp_path, monkeypatch):
    """环境变量覆盖的 ckpt 真的进入 workflow（验收 4 的失败注入方式）。"""
    project = "proj-ckpt"
    _write_inputs(tmp_path, project, ("SHOT_1",))
    monkeypatch.setenv("SCENE_RENDER_CKPT", "no-such-model.safetensors")
    seen: list[str] = []

    def fake_submit(base_url, workflow, timeout=120.0):
        seen.append(workflow["1"]["inputs"]["ckpt_name"])
        raise RuntimeError("ComfyUI 提交失败（HTTP 400）：value not in list: no-such-model.safetensors")

    monkeypatch.setattr(render.comfyui_video, "unload_ollama", lambda *a, **kw: [])
    monkeypatch.setattr(render.comfyui_video, "gpu_mb", lambda: 0)
    monkeypatch.setattr(render.comfyui_video, "submit", fake_submit)

    assert render.main(["--project", project, "--artifacts-dir", str(tmp_path),
                        "--render"]) == 0
    assert seen == ["no-such-model.safetensors"] * 2  # 1 次 + 1 次重试
    shot = _read_plan(tmp_path / project)["shots"][0]
    assert shot["status"] == "failed" and "no-such-model" in shot["error"]
