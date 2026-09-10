"""Studio Edit 分批改造（S2b）专项测试：分批边界 / 代码补跨批帧号 / 覆盖校验 / demo 兼容。

不触发真实网络：站级用 demo caller（AgentCaller(demo_mode=True)）或假 caller 喂预置 JSON。
"""
import argparse
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.editing_blueprint import EditingBlueprint
from schemas.script import Scene, Script
from schemas.shot_list import Shot, ShotList
from studios import agent_utils as au
from studios.studio_edit import run as edit


def _shot_list(spec: list[tuple[str, int]], duration: float = 2.0) -> ShotList:
    """按 [(scene_id, 镜数)] 构造 ShotList（每镜时长 duration 秒），供分批测试。"""
    shots: list[Shot] = []
    n = 0
    for scene_id, count in spec:
        for _ in range(count):
            n += 1
            shots.append(Shot(
                shot_id=f"SHOT_{n}", scene_id=scene_id, duration=duration,
                subject="主体", action="动作", emotion="平静", environment="环境",
                lighting="冷光", camera_angle="平视中景", camera_movement="固定",
                narrative_purpose="叙事",
            ))
    return ShotList(target_shots=len(shots), shots=shots)


def _script(scene_ids: list[str], duration_sec: float = 10.0) -> Script:
    """按 scene_id 列表构造 Script（各场时长 duration_sec），供分批边界对齐。"""
    return Script(
        title="分批测试", logline="梗概", emotional_curve=["平静", "紧张"],
        scenes=[
            Scene(scene_id=sid, location="地点", time_of_day="夜", summary="概要",
                  dialogue=None, emotional_arc="平静 → 紧张", duration_sec=duration_sec)
            for sid in scene_ids
        ],
    )


class _FakeEditorCaller:
    """假 editor caller：按批依次吐出预置响应（可用回调按 batch 序号定制）。"""

    def __init__(self, responder):
        self._responder = responder
        self.calls: list[str] = []

    def call(self, agent, soul, prompt):
        self.calls.append(prompt)
        return self._responder(len(self.calls), prompt)


# ── 1) 批次边界：与 shoot/prompt 同源（逐场），大场按镜组细分 ──

def test_editor_batches_follow_scene_boundary():
    """逐场分批：批次 = shot_list 的场景块，每批带本场 scene（供对齐情绪曲线）。"""
    shot_list = _shot_list([("SCENE_1", 2), ("SCENE_2", 3)])
    script = _script(["SCENE_1", "SCENE_2"])
    batches = edit._editor_batches(script, shot_list)
    assert [b["scene_id"] for b in batches] == ["SCENE_1", "SCENE_2"]
    assert [len(b["shots"]) for b in batches] == [2, 3]
    assert batches[0]["scene"]["scene_id"] == "SCENE_1"  # 本场 scene 注入
    assert [s.shot_id for s in batches[0]["shots"]] == ["SHOT_1", "SHOT_2"]


def test_editor_batches_subdivide_large_scene():
    """大场（镜数 > EDIT_SHOTS_PER_BATCH）按镜组细分，同 scene_id 出现多个连续批次。"""
    count = edit.EDIT_SHOTS_PER_BATCH + 2
    shot_list = _shot_list([("SCENE_1", count)])
    batches = edit._editor_batches(_script(["SCENE_1"]), shot_list)
    assert [b["scene_id"] for b in batches] == ["SCENE_1", "SCENE_1"]
    assert [len(b["shots"]) for b in batches] == [edit.EDIT_SHOTS_PER_BATCH, 2]


def test_editor_batches_tolerate_unknown_scene():
    """shot 的 scene_id 在 script 中缺失时 scene=None（不炸，帧号仍由代码补全）。"""
    shot_list = _shot_list([("SCENE_9", 1)])
    batches = edit._editor_batches(_script(["SCENE_1"]), shot_list)
    assert len(batches) == 1 and batches[0]["scene"] is None


# ── 2) 合并：代码补跨批帧号（不信模型自填）────────────────

def test_merge_editor_fills_frames_from_code():
    """帧号一律由代码按镜头顺序补：模型给的错乱帧号被覆盖，转场/音频保留，音轨落点合并。"""
    shot_list = _shot_list([("SCENE_1", 2), ("SCENE_2", 1)])  # 3 镜 × 2s × 24fps = 48 帧/镜
    results = [
        {  # 第 1 批：模型给了错乱帧号（应被覆盖）
            "target_fps": 24,
            "timeline": [
                {"shot_id": "SHOT_1", "start_frame": 999, "end_frame": 1000,
                 "transition_in": "Cut", "transition_out": "Cross Dissolve", "audio_event": "雨声"},
                {"shot_id": "SHOT_2", "start_frame": 7, "end_frame": 8,
                 "transition_in": "Fade", "transition_out": "Cut", "audio_event": None},
            ],
            "audio_beats": [{"time_sec": 1.5, "event": "鼓点"}, {"time_sec": 1.5, "event": "重复"}],
        },
        {  # 第 2 批：缺 target_fps（用首批值）；缺 transition 字段（回退 Cut）
            "timeline": [{"shot_id": "SHOT_3", "audio_event": "对白"}],
            "audio_beats": [{"time_sec": 0.5, "event": "开门"}],
        },
    ]
    merged = edit._merge_editor(shot_list, results)

    assert merged["target_fps"] == 24
    assert [(e["start_frame"], e["end_frame"]) for e in merged["timeline"]] == [
        (0, 48), (48, 96), (96, 144)]                    # 跨批帧号连续、无重叠
    assert merged["total_frames"] == 144                 # = 3 镜 × 48 帧
    assert [e["transition_out"] for e in merged["timeline"]][:1] == ["Cross Dissolve"]
    assert merged["timeline"][1]["transition_in"] == "Fade"
    assert merged["timeline"][2]["transition_in"] == "Cut"   # 缺省回退
    assert merged["timeline"][2]["audio_event"] == "对白"
    assert merged["audio_beats"] == [
        {"time_sec": 0.5, "event": "开门"}, {"time_sec": 1.5, "event": "鼓点"}]  # 去重 + 排序
    EditingBlueprint.model_validate(merged)              # 合并结果可过契约校验


def test_merge_editor_tolerates_non_dict_batch():
    """某批结果是顶层 list（raw safe_parse_json）时不抛 AttributeError（ocr 防护同源）。"""
    shot_list = _shot_list([("SCENE_1", 1)])
    results = [[{"shot_id": "SHOT_1"}], {"timeline": [{"shot_id": "SHOT_1"}]}]
    merged = edit._merge_editor(shot_list, results)
    assert len(merged["timeline"]) == 1


def test_merge_editor_missing_shot_raises():
    """缺任一镜的时间线条目 → 明确报错（不静默产出缺镜时间线）。"""
    shot_list = _shot_list([("SCENE_1", 2)])
    results = [{"timeline": [{"shot_id": "SHOT_1"}]}]
    with pytest.raises(RuntimeError) as excinfo:
        edit._merge_editor(shot_list, results)
    assert "SHOT_2" in str(excinfo.value)


# ── 3) 站级：分批跑通 + 覆盖校验 + demo 兼容 ─────────────

def test_build_artifact_demo_covers_all_shots():
    """demo 全量分批：timeline 条数 == 镜数、帧号连续、total_frames 与镜头总时长一致。"""
    shot_list = _shot_list([("SCENE_1", 3), ("SCENE_2", 4), ("SCENE_3", 2)])
    script = _script(["SCENE_1", "SCENE_2", "SCENE_3"])
    caller = au.AgentCaller(demo_mode=True)
    blueprint = edit.build_artifact(argparse.Namespace(), {"shoot": shot_list, "script": script}, caller)

    assert len(blueprint.timeline) == len(shot_list.shots) == 9
    frame = 0
    for entry in blueprint.timeline:
        assert entry.start_frame == frame          # 帧号连续
        frame = entry.end_frame
    expected_total = sum(max(1, int(round(s.duration * blueprint.target_fps)))
                         for s in shot_list.shots)
    assert blueprint.total_frames == frame == expected_total


def test_build_artifact_missing_coverage_raises():
    """某批反复漏镜（重试仍空）→ 批内校验汇总报错（含缺失 shot_id），不静默缺镜。"""
    shot_list = _shot_list([("SCENE_1", 2), ("SCENE_2", 1)])
    script = _script(["SCENE_1", "SCENE_2"])

    def responder(index, prompt):
        if index == 1:  # 第 1 批（SCENE_1）正常
            return json.dumps({
                "target_fps": 24,
                "timeline": [
                    {"shot_id": "SHOT_1", "transition_in": "Cut", "transition_out": "Cut"},
                    {"shot_id": "SHOT_2", "transition_in": "Cut", "transition_out": "Cut"},
                ],
                "audio_beats": [],
            })
        return json.dumps({"target_fps": 24, "timeline": [], "audio_beats": []})  # 第 2 批反复漏镜

    with pytest.raises(RuntimeError) as excinfo:
        edit.build_artifact(argparse.Namespace(), {"shoot": shot_list, "script": script},
                            _FakeEditorCaller(responder))
    assert "SHOT_3" in str(excinfo.value)


def test_build_artifact_retries_incomplete_batch(capsys):
    """某批首次漏镜 → 批内重试该批（补全后通过），不整站失败（S2c）。"""
    shot_list = _shot_list([("SCENE_1", 2), ("SCENE_2", 1)])
    script = _script(["SCENE_1", "SCENE_2"])

    def responder(index, prompt):
        # 第 2 批（SCENE_2）首次输出空 timeline（触发批内重试）；重发时（第 3 次调用）补齐
        if index == 3:
            return json.dumps({"target_fps": 24, "timeline": [
                {"shot_id": "SHOT_3", "transition_in": "Cut", "transition_out": "Cut"}],
                "audio_beats": []})
        if index == 2:
            return json.dumps({"target_fps": 24, "timeline": [], "audio_beats": []})
        return json.dumps({"target_fps": 24, "timeline": [
            {"shot_id": "SHOT_1", "transition_in": "Cut", "transition_out": "Cut"},
            {"shot_id": "SHOT_2", "transition_in": "Cut", "transition_out": "Cut"}],
            "audio_beats": []})

    blueprint = edit.build_artifact(argparse.Namespace(), {"shoot": shot_list, "script": script},
                                    _FakeEditorCaller(responder))
    assert [e.shot_id for e in blueprint.timeline] == ["SHOT_1", "SHOT_2", "SHOT_3"]
    assert "校验未过" in capsys.readouterr().out       # 批内重试日志可见


def test_batch_coverage_error_reports_missing_and_dict_safe():
    """批内覆盖校验：缺项返回含 shot_id 的消息；顶层 list / 非 dict 项不炸（dict-safe）。"""
    assert edit._batch_coverage_error(
        {"timeline": [{"shot_id": "SHOT_1"}, {"shot_id": "SHOT_2"}]}, ["SHOT_1", "SHOT_2"]) is None
    err = edit._batch_coverage_error({"timeline": [{"shot_id": "SHOT_1"}]}, ["SHOT_1", "SHOT_2"])
    assert err is not None and "SHOT_2" in err
    assert edit._batch_coverage_error([1, 2, 3], ["SHOT_1"]) is not None   # 顶层 list 安全


def test_build_artifact_no_key_message_preserved(monkeypatch, tmp_path):
    """无 key（NoKeyError）：站级 main 报错走可操作提示，不被「第 k/N 批失败」掩盖。"""
    monkeypatch.setenv("SCENE_ENV", "prod")          # 确保走 deepseek 分支（无 key → NoKeyError）
    monkeypatch.setattr(au, "get_api_key", lambda: None)
    project = tmp_path / "edit-nokey"
    (project / "03_shoot").mkdir(parents=True)
    (project / "01_script").mkdir(parents=True)
    shot_list = _shot_list([("SCENE_1", 2)])
    (project / "03_shoot" / "shot_list.json").write_text(
        json.dumps(shot_list.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    (project / "01_script" / "script.json").write_text(
        json.dumps(_script(["SCENE_1"]).model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")

    with pytest.raises(au.NoKeyError):
        edit.main(["--project", "edit-nokey", "--artifacts-dir", str(tmp_path)])


# ── 4) 产物覆盖/一致性校验（分批合并后最后一道防线）────────

def test_validate_blueprint_rejects_inconsistencies():
    """条数不符 / 帧号不连续 / total_frames 与末帧不一致 均报错；正常产物放行。"""
    shot_list = _shot_list([("SCENE_1", 2)])
    ok = EditingBlueprint.model_validate({
        "target_fps": 24,
        "timeline": [
            {"shot_id": "SHOT_1", "start_frame": 0, "end_frame": 48},
            {"shot_id": "SHOT_2", "start_frame": 48, "end_frame": 96},
        ],
        "total_frames": 96,
    })
    edit._validate_blueprint(ok, shot_list)  # 一致 → 不抛

    # 条数少于镜数（缺镜）— 覆盖校验
    short = ok.model_copy(update={"timeline": ok.timeline[:1], "total_frames": 48})
    with pytest.raises(RuntimeError, match="覆盖校验失败"):
        edit._validate_blueprint(short, shot_list)

    # 帧号不连续（跨批补帧出错）
    gap = EditingBlueprint.model_validate({
        "target_fps": 24,
        "timeline": [
            {"shot_id": "SHOT_1", "start_frame": 0, "end_frame": 48},
            {"shot_id": "SHOT_2", "start_frame": 60, "end_frame": 96},
        ],
        "total_frames": 96,
    })
    with pytest.raises(RuntimeError, match="帧号不连续"):
        edit._validate_blueprint(gap, shot_list)

    # total_frames 与末帧不一致
    bad_total = ok.model_copy(update={"total_frames": 100})
    with pytest.raises(RuntimeError, match="total_frames"):
        edit._validate_blueprint(bad_total, shot_list)


def test_merge_beats_dedups_near_equal_times():
    """相近浮点时间点的落点按毫秒精度去重（不因尾差并存两条）。"""
    merged = edit._merge_beats([
        {"audio_beats": [{"time_sec": 1.5, "event": "鼓点"}]},
        {"audio_beats": [{"time_sec": 1.50000001, "event": "重复"}, {"time_sec": 3, "event": "收束"}]},
    ])
    assert merged == [{"time_sec": 1.5, "event": "鼓点"}, {"time_sec": 3.0, "event": "收束"}]
