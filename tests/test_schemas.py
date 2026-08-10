"""各产物契约：demo 实例化 + 校验通过 + 序列化 round-trip。"""
import json

import pytest

from schemas.artifact import ArtifactBase
from schemas.editing_blueprint import EditingBlueprint
from schemas.prompt_list import PromptList
from schemas.script import DialogueLine, Script
from schemas.shot_list import Shot, ShotList
from schemas.visual_bible import VisualBible

# 所有产物契约类（继承 ArtifactBase，均有 demo()）
PRODUCT_MODELS = [Script, VisualBible, ShotList, PromptList, EditingBlueprint]


@pytest.mark.parametrize("model", PRODUCT_MODELS)
def test_demo_valid_and_round_trip(model):
    """demo 实例：校验通过、具备血缘字段、JSON round-trip 还原。"""
    inst = model.demo()
    assert isinstance(inst, ArtifactBase)
    assert inst.upstream_hash == {}
    assert inst.edited_by == "ai"
    data = json.loads(json.dumps(inst.model_dump(mode="json")))
    assert model.model_validate(data) == inst


def test_shot_id_pattern_enforced():
    """Shot.shot_id 必须匹配 ^SHOT_\\d+$。"""
    with pytest.raises(Exception):
        Shot(
            shot_id="bad_id",
            scene_id="SCENE_1",
            duration=1.0,
            subject="s",
            action="a",
            emotion="e",
            environment="env",
            lighting="l",
            camera_angle="c",
            camera_movement="m",
            narrative_purpose="n",
        )


def test_scene_id_pattern_enforced():
    """Scene.scene_id 必须匹配 ^SCENE_\\d+$。"""
    from schemas.script import Scene

    with pytest.raises(Exception):
        Scene(scene_id="bad", location="l", time_of_day="t", summary="s", emotional_arc="e", duration_sec=1.0)


def test_script_dialogue_is_dialogue_line_list():
    """Phase B.1 契约：Scene.dialogue 为 list[DialogueLine]（多轮对白），非 str。"""
    script = Script.demo()
    assert script.scenes[0].dialogue is not None  # demo 首场含对白
    for scene in script.scenes:
        if scene.dialogue is not None:
            assert isinstance(scene.dialogue, list)
            for line in scene.dialogue:
                assert isinstance(line, DialogueLine)
                assert line.speaker and line.line
    # 多轮结构校验：非法类型（str）应被拒绝
    with pytest.raises(Exception):
        Script.model_validate({
            **script.model_dump(mode="json"),
            "scenes": [{
                **script.scenes[0].model_dump(mode="json"),
                "dialogue": "「这么晚了，买什么？」",  # 旧结构 str 不再合法
            }],
        })


def test_visual_bible_structure():
    """VisualBible 有完整结构：色彩/材质/光照/角色造型/备注。"""
    vb = VisualBible.demo()
    assert vb.color_palette.primary
    assert vb.material_style
    assert vb.lighting_style
    assert len(vb.character_designs) >= 1
    assert isinstance(vb.art_notes, list)
