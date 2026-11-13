"""sc_contracts — SceneCraft 产物契约包（pydantic v2）

M0 抽包：由仓库原 `schemas/` 原样搬迁而来（文件与字段语义不变），
主仓 `schemas/` 保留为薄转发层，旧 import 路径继续有效。

模块划分（与主仓 schemas/ 一一对应）：
    artifact.py            ArtifactBase（血缘基类）+ content_hash()
    script.py              Script / Scene / DialogueLine
    visual_bible.py        VisualBible / ColorPalette / CharacterDesign
    shot_list.py           ShotList / Shot
    prompt_list.py         PromptList / ShotPrompt
    editing_blueprint.py   EditingBlueprint / TimelineEntry / AudioBeat
    render_plan.py         RenderPlan / RenderShot
    qc_report.py           QcReport / QcFinding
    manifest.py            Manifest / StudioStatus（项目台账，非产物）

最小用法：
    from sc_contracts import Script, ShotList
    model = ShotList.model_validate(data)
"""
from sc_contracts.artifact import ArtifactBase, content_hash
from sc_contracts.editing_blueprint import AudioBeat, EditingBlueprint, TimelineEntry
from sc_contracts.manifest import Manifest, StudioStatus
from sc_contracts.prompt_list import PromptList, ShotPrompt
from sc_contracts.qc_report import QcFinding, QcReport
from sc_contracts.render_plan import RenderPlan, RenderShot
from sc_contracts.script import DialogueLine, Scene, Script
from sc_contracts.shot_list import Shot, ShotList
from sc_contracts.visual_bible import CharacterDesign, ColorPalette, VisualBible

__all__ = [
    "ArtifactBase",
    "content_hash",
    "Script",
    "Scene",
    "DialogueLine",
    "VisualBible",
    "ColorPalette",
    "CharacterDesign",
    "ShotList",
    "Shot",
    "PromptList",
    "ShotPrompt",
    "EditingBlueprint",
    "TimelineEntry",
    "AudioBeat",
    "RenderPlan",
    "RenderShot",
    "QcReport",
    "QcFinding",
    "Manifest",
    "StudioStatus",
]
