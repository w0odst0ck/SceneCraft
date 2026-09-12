"""scripts/comfyui_video.py（LTX 渲染客户端）单测：workflow 构造 + 提交/轮询/下载 + 失败态。

全部不触发真实网络与 GPU：HTTP 层（_post_json/_get_json/_get_bytes）与 nvidia-smi 打桩。
"""
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import comfyui_video as cv  # noqa: E402


# ── workflow 构造 ────────────────────────────────────

def _refs(workflow: dict) -> list[str]:
    """收集 workflow 内所有 [node_id, index] 形式的连接引用（node_id 一侧）。"""
    refs: list[str] = []
    for node in workflow.values():
        for value in node["inputs"].values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                refs.append(value[0])
    return refs


def test_build_ltxv_workflow_structure():
    """节点齐备、参数透传、连线指向正确节点（与 spike 已验证图一致）。"""
    wf = cv.build_ltxv_workflow("正提示", "负提示", 1024, 576, 49, 30, 3.0, 42, 25.0,
                               "ltx-video-2b-v0.9.5.safetensors")

    assert set(wf) == {str(i) for i in range(1, 12)}
    assert wf["1"]["class_type"] == "CheckpointLoaderSimple"
    assert wf["1"]["inputs"] == {"ckpt_name": "ltx-video-2b-v0.9.5.safetensors"}
    assert wf["2"]["class_type"] == "CLIPLoader"
    assert wf["2"]["inputs"] == {"clip_name": cv.TEXT_ENCODER, "type": "ltxv"}
    # 正/负提示词分别进 3/4 号 encode，且共用同一 CLIP
    assert wf["3"]["inputs"] == {"text": "正提示", "clip": ["2", 0]}
    assert wf["4"]["inputs"] == {"text": "负提示", "clip": ["2", 0]}
    assert wf["5"]["class_type"] == "LTXVConditioning"
    assert wf["5"]["inputs"] == {"positive": ["3", 0], "negative": ["4", 0], "frame_rate": 25.0}
    assert wf["6"]["inputs"] == {"width": 1024, "height": 576, "length": 49, "batch_size": 1}
    assert wf["7"]["class_type"] == "LTXVScheduler"
    assert wf["7"]["inputs"]["steps"] == 30
    assert wf["7"]["inputs"]["latent"] == ["6", 0]
    assert wf["8"]["inputs"] == {"sampler_name": "euler"}
    sampler = wf["9"]["inputs"]
    assert sampler["model"] == ["1", 0] and sampler["add_noise"] is True
    assert sampler["noise_seed"] == 42 and sampler["cfg"] == 3.0
    assert sampler["positive"] == ["5", 0] and sampler["negative"] == ["5", 1]
    assert sampler["sampler"] == ["8", 0] and sampler["sigmas"] == ["7", 0]
    assert sampler["latent_image"] == ["6", 0]
    assert wf["10"]["inputs"] == {"samples": ["9", 0], "vae": ["1", 2]}  # VAE 取自 checkpoint
    assert wf["11"]["class_type"] == "SaveWEBM"
    assert wf["11"]["inputs"]["images"] == ["10", 0]
    assert wf["11"]["inputs"]["filename_prefix"] == cv.FILENAME_PREFIX
    assert wf["11"]["inputs"]["fps"] == 25.0
    # 所有连线都指向存在的节点；整体可 JSON 序列化（要 POST 给 ComfyUI）
    assert all(ref in wf for ref in _refs(wf))
    assert json.loads(json.dumps(wf))["9"]["class_type"] == "SamplerCustom"


def test_build_ltxv_workflow_reflects_params():
    """分辨率/帧数/步数/cfg/种子/fps 均按实参进入 workflow（无硬编码残留）。"""
    wf = cv.build_ltxv_workflow("p", "n", 768, 512, 121, 20, 2.5, 7, 24.0, "other.safetensors")
    assert wf["1"]["inputs"]["ckpt_name"] == "other.safetensors"
    assert wf["6"]["inputs"]["width"] == 768 and wf["6"]["inputs"]["height"] == 512
    assert wf["6"]["inputs"]["length"] == 121
    assert wf["7"]["inputs"]["steps"] == 20
    assert wf["9"]["inputs"]["cfg"] == 2.5 and wf["9"]["inputs"]["noise_seed"] == 7
    assert wf["5"]["inputs"]["frame_rate"] == 24.0 and wf["11"]["inputs"]["fps"] == 24.0


# ── 提交（/prompt）───────────────────────────────────

def test_submit_returns_prompt_id(monkeypatch):
    seen = {}

    def fake_post(url, payload, timeout=120.0):
        seen["url"] = url
        seen["payload"] = payload
        return {"prompt_id": "pid-1"}

    monkeypatch.setattr(cv, "_post_json", fake_post)
    assert cv.submit("http://127.0.0.1:8188", {"1": {"class_type": "X", "inputs": {}}}) == "pid-1"
    assert seen["url"] == "http://127.0.0.1:8188/prompt"
    assert seen["payload"]["prompt"]["1"]["class_type"] == "X"


def test_submit_wraps_unreachable(monkeypatch):
    """ComfyUI 不可达 → RuntimeError（消息含地址），不泄漏底层异常类型。"""
    def boom(url, payload, timeout=120.0):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(cv, "_post_json", boom)
    with pytest.raises(RuntimeError, match="不可达"):
        cv.submit("http://127.0.0.1:8188", {})


def test_submit_requires_prompt_id(monkeypatch):
    monkeypatch.setattr(cv, "_post_json", lambda url, payload, timeout=120.0: {"error": "bad"})
    with pytest.raises(RuntimeError, match="prompt_id"):
        cv.submit("http://x", {})


# ── 轮询 + 下载 ─────────────────────────────────────

def _history(prompt_id: str, status: str, outputs: dict) -> dict:
    return {prompt_id: {"status": {"status_str": status}, "outputs": outputs}}


def _webm_output(name: str = "scene_render_00001.webm", subfolder: str = "") -> dict:
    return {"11": {"images": [{"filename": name, "subfolder": subfolder, "type": "output"}]}}


def test_wait_and_download_copies_and_renames(tmp_path, monkeypatch):
    """任务成功 → 从 ComfyUI output 目录 copy 产物，首个产物按 target_stem 改名。"""
    comfy_out = tmp_path / "comfy_output"
    comfy_out.mkdir()
    (comfy_out / "scene_render_00001.webm").write_bytes(b"fake-webm")
    monkeypatch.setattr(cv, "_get_json",
                        lambda url, timeout=60.0: _history("pid1", "success", _webm_output()))
    monkeypatch.setattr(cv, "gpu_mb", lambda: 11061)

    out_dir = tmp_path / "out"
    files = cv.wait_and_download("http://x", "pid1", out_dir, poll=0, max_wait=30,
                                 target_stem="SHOT_1", comfy_output=comfy_out)

    assert files == [out_dir / "SHOT_1.webm"]
    assert (out_dir / "SHOT_1.webm").read_bytes() == b"fake-webm"
    run = cv.last_run()
    assert run["prompt_id"] == "pid1"
    assert run["peak_vram_mb"] == 11061
    assert run["duration_sec"] >= 0
    assert run["files"] == [str(out_dir / "SHOT_1.webm")]


def test_wait_and_download_keeps_original_name_without_stem(tmp_path, monkeypatch):
    """不指定 target_stem 时保留 ComfyUI 原名；子目录产物也能定位。"""
    comfy_out = tmp_path / "comfy_output"
    (comfy_out / "sub").mkdir(parents=True)
    (comfy_out / "sub" / "keep_00002.webm").write_bytes(b"x")
    monkeypatch.setattr(cv, "_get_json", lambda url, timeout=60.0: _history(
        "pid2", "success", _webm_output("keep_00002.webm", subfolder="sub")))
    monkeypatch.setattr(cv, "gpu_mb", lambda: -1)

    files = cv.wait_and_download("http://x", "pid2", tmp_path / "o", poll=0,
                                 comfy_output=comfy_out)
    assert files == [tmp_path / "o" / "keep_00002.webm"]
    assert files[0].exists()
    assert cv.last_run()["peak_vram_mb"] == -1  # 采样不可用时如实记录 -1


def test_wait_and_download_view_fallback(tmp_path, monkeypatch):
    """本地 output 目录不可见（远程/容器）→ 走 /view API 下载。"""
    monkeypatch.setattr(cv, "_get_json",
                        lambda url, timeout=60.0: _history("pid3", "success", _webm_output()))
    monkeypatch.setattr(cv, "gpu_mb", lambda: 0)
    monkeypatch.setattr(cv, "_get_bytes", lambda url, timeout=300.0: b"from-view")

    files = cv.wait_and_download("http://x", "pid3", tmp_path / "o", poll=0,
                                 comfy_output=tmp_path / "nonexistent")
    assert files[0].read_bytes() == b"from-view"


def test_wait_and_download_failed_status_raises(tmp_path, monkeypatch):
    """ComfyUI 任务状态非 success → RuntimeError（含状态详情，不静默）。"""
    monkeypatch.setattr(cv, "_get_json", lambda url, timeout=60.0: _history(
        "pid4", "error", {"11": {"images": []}}))
    monkeypatch.setattr(cv, "gpu_mb", lambda: 9000)
    with pytest.raises(RuntimeError, match="error"):
        cv.wait_and_download("http://x", "pid4", tmp_path / "o", poll=0, max_wait=30)
    assert cv.last_run()["peak_vram_mb"] == 9000  # 失败也留档


def test_wait_and_download_success_but_no_output_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(cv, "_get_json",
                        lambda url, timeout=60.0: _history("pid5", "success", {}))
    monkeypatch.setattr(cv, "gpu_mb", lambda: 0)
    with pytest.raises(RuntimeError, match="未找到产物"):
        cv.wait_and_download("http://x", "pid5", tmp_path / "o", poll=0, max_wait=30)


def test_wait_and_download_timeout(tmp_path, monkeypatch):
    """超过 max_wait 仍未完成 → RuntimeError（含峰值显存，便于定位）。"""
    monkeypatch.setattr(cv, "_get_json", lambda url, timeout=60.0: {})
    monkeypatch.setattr(cv, "gpu_mb", lambda: -1)
    with pytest.raises(RuntimeError, match="超时"):
        cv.wait_and_download("http://x", "pid6", tmp_path / "o", poll=0, max_wait=0)


def test_wait_and_download_timeout_interrupts_remote_task(tmp_path, monkeypatch):
    """超时先 POST /interrupt + /queue 删残留任务：否则重试会与新任务叠加（12GB 卡必 OOM）。"""
    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(cv, "_get_json", lambda url, timeout=60.0: {})
    monkeypatch.setattr(cv, "gpu_mb", lambda: -1)
    monkeypatch.setattr(cv, "_post_json",
                        lambda url, payload, timeout=120.0: posts.append((url, payload)) or {})
    with pytest.raises(RuntimeError, match="超时"):
        cv.wait_and_download("http://x", "pid-timeout", tmp_path / "o", poll=0, max_wait=0)
    assert posts == [("http://x/interrupt", {}), ("http://x/queue", {"delete": ["pid-timeout"]})]


def test_wait_and_download_reports_download_error(tmp_path, monkeypatch):
    """无产物时把首个下载错误并入报错信息（不静默吞掉根因）。"""
    monkeypatch.setattr(cv, "_get_json", lambda url, timeout=60.0: _history(
        "pid7", "success", _webm_output("missing.webm")))
    monkeypatch.setattr(cv, "gpu_mb", lambda: 0)

    def boom(url, timeout=300.0):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(cv, "_get_bytes", boom)
    with pytest.raises(RuntimeError, match="首个下载错误") as excinfo:
        cv.wait_and_download("http://x", "pid7", tmp_path / "o", poll=0,
                             comfy_output=tmp_path / "nonexistent")
    assert "404" in str(excinfo.value)


def test_view_fallback_keeps_item_type_and_subfolder(tmp_path, monkeypatch):
    """/view 兜底须带产物原始 type/subfolder（temp 产物硬编码 output 会 404）。"""
    urls: list[str] = []

    def fake_bytes(url, timeout=300.0):
        urls.append(url)
        return b"tmp"

    monkeypatch.setattr(cv, "_get_json", lambda url, timeout=60.0: _history(
        "pid8", "success",
        {"11": {"images": [{"filename": "temp.webm", "subfolder": "s", "type": "temp"}]}}))
    monkeypatch.setattr(cv, "gpu_mb", lambda: 0)
    monkeypatch.setattr(cv, "_get_bytes", fake_bytes)

    files = cv.wait_and_download("http://x", "pid8", tmp_path / "o", poll=0,
                                 comfy_output=tmp_path / "nonexistent")
    assert files and files[0].read_bytes() == b"tmp"
    assert "type=temp" in urls[0] and "subfolder=s" in urls[0]


# ── 中断残留任务 ─────────────────────────────────────

def test_interrupt_posts_to_endpoint(monkeypatch):
    """默认只中断执行中的任务；给 prompt_id 时额外清掉仍在排队的同一任务。"""
    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(cv, "_post_json",
                        lambda url, payload, timeout=120.0: posts.append((url, payload)) or {})

    assert cv.interrupt("http://x") is True
    assert posts == [("http://x/interrupt", {})]

    posts.clear()
    assert cv.interrupt("http://x", "pid-1") is True
    assert posts == [("http://x/interrupt", {}), ("http://x/queue", {"delete": ["pid-1"]})]


def test_interrupt_never_raises(monkeypatch):
    """中断是尽力而为：ComfyUI 不可达时返回 False，不掩盖原始错误。"""
    def boom(url, payload, timeout=120.0):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(cv, "_post_json", boom)
    assert cv.interrupt("http://x", "pid-1") is False


# ── ollama 卸载与显存采样 ────────────────────────────

def test_unload_ollama_unloads_each_loaded_model(monkeypatch):
    monkeypatch.setattr(cv, "_get_json", lambda url, timeout=60.0: {
        "models": [{"name": "qwen3:14b-ctx2k"}, {"name": ""}, "junk"]})
    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(cv, "_post_json",
                        lambda url, payload, timeout=120.0: posts.append((url, payload)) or {})
    assert cv.unload_ollama("http://ollama") == ["qwen3:14b-ctx2k"]
    assert posts == [("http://ollama/api/generate",
                      {"model": "qwen3:14b-ctx2k", "prompt": "", "keep_alive": 0})]


def test_unload_ollama_tolerates_service_down(monkeypatch):
    """ollama 不可达时返回空列表，不抛异常（显存卸载是尽力而为）。"""
    def boom(url, timeout=60.0):
        raise urllib.error.URLError("ollama down")

    monkeypatch.setattr(cv, "_get_json", boom)
    assert cv.unload_ollama() == []


def test_gpu_mb_returns_minus_one_on_failure(monkeypatch):
    """nvidia-smi 缺失/报错时返回 -1（不抛异常，避免打断轮询）。"""
    def boom(*args, **kwargs):
        raise OSError("nvidia-smi not found")

    monkeypatch.setattr(cv.subprocess, "run", boom)
    assert cv.gpu_mb() == -1


def test_gpu_mb_parses_max_of_gpus(monkeypatch):
    class Proc:
        stdout = "1024\n11061\n"
        returncode = 0

    monkeypatch.setattr(cv.subprocess, "run", lambda *a, **k: Proc())
    assert cv.gpu_mb() == 11061


# ── 一站式出片 + CLI ────────────────────────────────

def test_render_clip_pipeline(tmp_path, monkeypatch):
    """render_clip：先卸 ollama，再提交，再轮询下载（顺序与返回值）。"""
    order: list[str] = []
    monkeypatch.setattr(cv, "unload_ollama", lambda: order.append("unload") or ["m"])
    monkeypatch.setattr(cv, "gpu_mb", lambda: 123)
    monkeypatch.setattr(cv, "submit",
                        lambda base_url, wf, timeout=120.0: order.append("submit") or "pid")
    monkeypatch.setattr(cv, "wait_and_download",
                        lambda base_url, pid, out_dir, **kw: order.append("download")
                        or [Path(out_dir) / "x.webm"])

    files = cv.render_clip("提示", tmp_path, ckpt="c.safetensors", base_url="http://x")
    assert order == ["unload", "submit", "download"]
    assert files == [tmp_path / "x.webm"]


def test_cli_main_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cv, "render_clip",
                        lambda *a, **kw: [tmp_path / "clip.webm"])
    monkeypatch.setattr(cv, "last_run", lambda: {"peak_vram_mb": 11061})
    (tmp_path / "clip.webm").write_bytes(b"z")

    assert cv.main(["提示词", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "峰值显存 11061 MiB" in out and "clip.webm" in out


def test_cli_main_failure_returns_1(tmp_path, monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise RuntimeError("ComfyUI 不可达（http://x）")

    monkeypatch.setattr(cv, "render_clip", boom)
    assert cv.main(["提示词", "--out", str(tmp_path)]) == 1
    assert "出片失败" in capsys.readouterr().err
