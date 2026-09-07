"""GPU 模型调度器单测：全部 mock 子进程（_run），不触碰真实 ollama/nvidia-smi。

覆盖：CLI stage 解析、load 预热+verify、verify 不达标 exit 2、free 幂等与逐个卸载。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import model_scheduler as ms  # noqa: E402


def _cp(args, rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, rc, stdout=stdout, stderr=stderr)


def _install_fake_run(monkeypatch, script=None, record=None):
    """按脚本表 mock _run：curl /api/ps → script['ps']；nvidia-smi → script['vram']。"""
    script = script or {}
    calls = []
    calls_ref = record if record is not None else calls

    def fake(args, **kwargs):
        calls_ref.append(list(args))
        joined = " ".join(args)
        if args and args[0] == "curl":
            if "api/ps" in joined:
                body = script.get("ps", {"models": []})
                return _cp(args, stdout=json.dumps(body))
            if "api/generate" in joined:
                if script.get("generate_fail"):
                    return _cp(args, rc=22, stderr="curl: (22) 服务器返回错误")
                return _cp(args, stdout="{}")
            return _cp(args, stdout="{}")
        if args and args[0] == "nvidia-smi":
            if script.get("smi_fail"):
                return _cp(args, rc=1, stderr="nvidia-smi: not found")
            return _cp(args, stdout=script.get("vram", "0"))
        return _cp(args, stdout="{}")

    monkeypatch.setattr(ms, "_run", fake)
    return calls_ref


def _generate_payloads(calls):
    """从记录的调用里抽出 /api/generate 的 -d JSON 载荷。"""
    out = []
    for args in calls:
        if "api/generate" in " ".join(args) and "-d" in args:
            out.append(json.loads(args[args.index("-d") + 1]))
    return out


def test_stage_llm14b_warmups_then_verifies_ok(monkeypatch, capsys):
    """llm-14b：先 ollama 预热（keep_alive 30m），再 nvidia-smi verify 达标 → exit 0。"""
    calls = _install_fake_run(monkeypatch, {"vram": "9123"})
    rc = ms.main(["stage", "llm-14b", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"stage": "llm-14b", "model": "qwen3:14b-ctx2k",
                   "released": [], "vram_mb": 9123, "ok": True}
    # 预热恰好一次，载荷符合 spec
    warmups = _generate_payloads(calls)
    assert len(warmups) == 1
    assert warmups[0]["model"] == "qwen3:14b-ctx2k"
    assert warmups[0]["prompt"] == ""
    assert warmups[0]["keep_alive"] == "30m"
    assert warmups[0]["stream"] is False
    # nvidia-smi 查询使用预期参数
    smi = [a for a in calls if a[0] == "nvidia-smi"]
    assert smi and "--query-gpu=memory.used" in smi[0]


def test_stage_llm9b_verify_below_threshold_exits_2(monkeypatch, capsys):
    """预热成功但显存不达标（2048MB < 5000MB 下限）→ exit 2、ok=false。"""
    _install_fake_run(monkeypatch, {"vram": "2048"})
    rc = ms.main(["stage", "llm-9b", "--json"])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["model"] == "qwen3.5:9b"
    assert out["vram_mb"] == 2048
    assert out["released"] == []


def test_free_idempotent_when_nothing_loaded(monkeypatch, capsys):
    """/api/ps 空 → free 成功 released=[]；重复 free 依然成功（幂等）。"""
    calls = _install_fake_run(monkeypatch, {"ps": {"models": []}})
    rc1 = ms.main(["stage", "free", "--json"])
    assert rc1 == 0
    out1 = json.loads(capsys.readouterr().out)
    assert out1 == {"stage": "free", "model": None, "released": [],
                    "vram_mb": 0, "ok": True}
    rc2 = ms.main(["stage", "free", "--json"])
    assert rc2 == 0
    out2 = json.loads(capsys.readouterr().out)
    assert out2["released"] == [] and out2["ok"] is True
    # release 别名同样幂等
    rc3 = ms.main(["stage", "release", "--json"])
    assert rc3 == 0
    # 未发出任何卸载 generate 请求
    assert _generate_payloads(calls) == []


def test_free_unloads_each_loaded_model(monkeypatch, capsys):
    """/api/ps 返回两个已加载模型 → 逐个 keep_alive=0 卸载并记录 released。"""
    ps = {"models": [{"name": "qwen3:14b-ctx2k"}, {"name": "qwen3.5:9b"}]}
    calls = _install_fake_run(monkeypatch, {"ps": ps, "vram": "6144"})
    rc = ms.main(["stage", "free", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["released"] == ["qwen3:14b-ctx2k", "qwen3.5:9b"]
    assert out["ok"] is True
    unloads = _generate_payloads(calls)
    assert [u["model"] for u in unloads] == ["qwen3:14b-ctx2k", "qwen3.5:9b"]
    assert all(u["keep_alive"] == 0 for u in unloads)


def test_unknown_stage_rejected_by_cli():
    """非法 stage → argparse exit 2。"""
    with pytest.raises(SystemExit) as exc:
        ms.main(["stage", "nope"])
    assert exc.value.code == 2


def test_ollama_down_stage_load_reports_error(monkeypatch, capsys):
    """ollama 不可达（curl 失败）→ exit 1、json ok=false + error 字段。"""
    _install_fake_run(monkeypatch, {"generate_fail": True})
    rc = ms.main(["stage", "llm-9b", "--json"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "error" in out


def test_reserved_stage_skips_warmup_but_verifies(monkeypatch, capsys):
    """video-wan 为预留占位：不做 ollama 预热，仅 nvidia-smi verify 档位。"""
    calls = _install_fake_run(monkeypatch, {"vram": "5123"})
    rc = ms.main(["stage", "video-wan", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["model"] == "wan21-t2v-1.3b"
    assert out["vram_mb"] == 5123 and out["ok"] is True
    assert _generate_payloads(calls) == []  # 无任何 ollama generate 调用
