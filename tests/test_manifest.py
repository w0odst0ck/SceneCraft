"""Manifest / StudioStatus 状态流转 + 序列化 round-trip。"""
import pytest

from schemas.manifest import Manifest, StudioStatus


def test_status_transition_done_to_manual_edited():
    """done → manual_edited 可切换（人工修改产物后标记，防 AI 重跑覆盖）。"""
    st = StudioStatus(status="done", version=2, output_hash="abc123")
    st.status = "manual_edited"
    assert st.status == "manual_edited"
    assert st.version == 2  # 切换状态不丢失版本信息


def test_manifest_round_trip():
    """Manifest 序列化 round-trip：model_dump(mode=json) → model_validate 还原。"""
    m = Manifest(
        project_id="demo1",
        created_at="2026-01-01T00:00:00+00:00",
        studios={
            "script": StudioStatus(status="done", output_hash="abc", upstream_hash={"x": "y"}),
            "art": StudioStatus(),
        },
        current_focus="script",
    )
    data = m.model_dump(mode="json")
    m2 = Manifest.model_validate(data)
    assert m2 == m
    assert m2.studios["script"].status == "done"
    assert m2.studios["art"].status == "pending"
    assert m2.current_focus == "script"


def test_studio_status_rejects_unknown_status():
    """status 枚举之外的值校验失败。"""
    with pytest.raises(Exception):
        StudioStatus(status="weird")
