"""ArtifactBase 血缘字段默认值 + compute_hash 稳定性。"""
from schemas.artifact import ArtifactBase
from schemas.script import Script


def test_defaults():
    """血缘字段默认值：upstream_hash 空 dict、edited_by=ai、version=1、output_hash=None。"""
    a = ArtifactBase()
    assert a.upstream_hash == {}
    assert a.edited_by == "ai"
    assert a.version == 1
    assert a.output_hash is None


def test_compute_hash_same_content_same_hash():
    """同内容必同 hash（稳定性）。"""
    a = Script.demo()
    b = a.model_copy()
    assert a.compute_hash() == b.compute_hash()


def test_compute_hash_differs_by_content():
    """内容不同则 hash 不同。"""
    a = Script.demo()
    b = a.model_copy(update={"title": "另一部剧"})
    assert a.compute_hash() != b.compute_hash()


def test_compute_hash_ignores_output_hash():
    """output_hash 由内容计算，不应参与自身 hash（避免写盘回填后 hash 漂移）。"""
    a = Script.demo()
    h = a.compute_hash()
    a.output_hash = h
    assert a.compute_hash() == h
