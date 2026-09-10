"""Studio Shoot 分批合并（S2/S2b）专项测试：批次级空产出报错 / 细化合并类型防护。

不触发真实网络：直接调用站内合并纯函数（_merge_director / _merge_maps）。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studios.studio_shoot import run as shoot


def _meta(scene_id: str, group_index: int = 1, group_total: int = 1) -> dict:
    return {"scene_id": scene_id, "group_index": group_index, "group_total": group_total}


def test_merge_director_renumbers_and_assigns_scene():
    """合并：shot_id 全局连续重写、scene_id 按批次归属、target_shots = 实际总数。"""
    metas = [_meta("SCENE_1"), _meta("SCENE_2")]
    results = [
        {"shots": [{"shot_id": "乱填", "scene_id": "SCENE_9"}, {"shot_id": "乱填"}]},
        {"shots": [{"shot_id": "乱填"}]},
    ]
    merged = shoot._merge_director(metas, results)
    assert merged["target_shots"] == 3
    assert [s["shot_id"] for s in merged["shots"]] == ["SHOT_1", "SHOT_2", "SHOT_3"]
    assert [s["scene_id"] for s in merged["shots"]] == ["SCENE_1", "SCENE_1", "SCENE_2"]


def test_merge_director_empty_subgroup_raises():
    """大场细分：某组 0 镜不得被同场兄弟组掩盖 → 按批次报错并带组序号。"""
    metas = [_meta("SCENE_1", 1, 2), _meta("SCENE_1", 2, 2)]
    results = [
        {"shots": [{"shot_id": "x"}, {"shot_id": "y"}]},
        {"shots": []},                       # 第 2 组空产出
    ]
    with pytest.raises(RuntimeError) as excinfo:
        shoot._merge_director(metas, results)
    assert "SCENE_1 第 2/2 组" in str(excinfo.value)


def test_merge_director_list_result_counts_as_empty_batch():
    """批次结果是顶层 list（raw safe_parse_json）→ 记为空的批次并报错，不静默跳过。"""
    with pytest.raises(RuntimeError, match="SCENE_1"):
        shoot._merge_director([_meta("SCENE_1")], [[{"shot_id": "SHOT_1"}]])


def test_merge_maps_rejects_non_dict_batch():
    """细化批次结果非 dict → 报错（不静默丢弃该批细化，可定位到批次号）。"""
    with pytest.raises(RuntimeError, match="第 2 批"):
        shoot._merge_maps([{"SHOT_1": {"camera_angle": "平视"}}, ["SHOT_2"]])


def test_merge_maps_skips_non_dict_values():
    """批内非 dict 的值不采纳（下游对未覆盖镜打印告警），合法值正常合并。"""
    merged = shoot._merge_maps([{"SHOT_1": {"camera_angle": "平视"}, "SHOT_2": "不是对象"}])
    assert merged == {"SHOT_1": {"camera_angle": "平视"}}
