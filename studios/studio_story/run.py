"""Studio Story — 剧本站（归入 Agent：producer + writer）

输入产物：无（输入为用户概念 concept 字符串，经 --concept 必填传入）
Agent 调用链：
  1. producer  接收 concept → 输出 MissionPlan 字段（类型/时长/镜头数/情绪基调）
  2. writer    接收 MissionPlan → 输出完整剧本 Script（title/logline/scenes/emotional_curve）
输出产物：<artifacts>/<project_id>/01_script/script.json（契约 schemas/script.py::Script）
manifest key：script ↔ 磁盘目录 01_script（映射见 SKILL.md）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

# 允许从仓库根目录导入顶层 schemas/（无论从哪个 cwd 调用本脚本）
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# story-materials 素材卡 pick 脚本（惰性导入：缺失时置 None，由 _materials_injection fail-closed）
MATERIALS_SCRIPTS = ROOT / "story-materials" / "scripts"
if str(MATERIALS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(MATERIALS_SCRIPTS))
try:
    import pick_materials
except ImportError:
    pick_materials = None  # type: ignore[assignment]

from schemas.script import Script
from studios import common
from studios.agent_utils import JSONParseError, NoKeyError, AgentCaller, append_output_contract, call_agent_json

STUDIO_KEY = "script"  # manifest 短名（= 输出 stage 短名）
OUTPUT_FILE = "script.json"
# 输入产物列表：本工作室无上游产物
INPUTS: list[tuple[str, str, type]] = []
SOUL_DIR = Path(__file__).parent / "agents"  # producer.md / writer.md

# 素材注入段头（pick_materials 返回的正文不带标题，由本处套上，避免两处重复）
MATERIALS_HEADER = "## 参考素材（与 concept 冲突时以 concept 为准）\n\n"


def _materials_injection(material_tags: str | None) -> str:
    """--material-tags 命中素材时生成注入段（置于 MissionPlan 之后）；空 tags 返回空串。

    纯函数（不触 IO、不依赖 args），可单测；总长 ≤2000（body 预算 = LIMIT - 头长）。
    pick_materials 脚本缺失时 fail-closed 抛 RuntimeError（E10），不静默降级。
    """
    if not material_tags or not material_tags.strip():
        return ""
    if pick_materials is None:
        raise RuntimeError(
            "--material-tags 已指定，但 story-materials/scripts/pick_materials.py 缺失，"
            "拒绝静默降级（fail-closed）。")
    body = pick_materials.pick_materials(
        material_tags, limit=pick_materials.LIMIT - len(MATERIALS_HEADER))
    return (MATERIALS_HEADER + body) if body.strip() else ""


def build_artifact(args: Any, inputs: dict[str, Any], caller: AgentCaller) -> Script:
    """producer → writer：概念拆解为 MissionPlan 字段，再生成完整剧本。"""
    # 1) producer：concept → MissionPlan 字段（不落盘，仅作 writer 输入）
    mission = call_agent_json(caller, "producer", "producer", args.concept)
    print(f"   ✅ MissionPlan: {mission.get('genre', '?')} / {mission.get('target_shots', '?')} 镜 / "
          f"{mission.get('target_duration_sec', '?')}s")
    # 2) writer：MissionPlan → Script（注入 Script 契约示例，约束真实输出格式）
    user_prompt = json.dumps(mission, ensure_ascii=False)
    injection = _materials_injection(getattr(args, "material_tags", None))
    if injection:
        user_prompt += "\n\n" + injection
    user_prompt = append_output_contract(
        user_prompt,
        json.dumps(Script.demo().model_dump(mode="json"), ensure_ascii=False),
    )
    return call_agent_json(caller, "writer", "writer", user_prompt, model_class=Script)


def main(argv: list[str] | None = None) -> int:
    parser = common.build_parser("Studio Story：剧本站（producer + writer）", concept=True)
    parser.add_argument(
        "--material-tags",
        default=None,
        help="素材标签（逗号分隔），命中则注入 writer 参考素材；不传行为不变",
    )
    args = parser.parse_args(argv)
    if not args.concept or args.concept.startswith("TODO_PHASE_B"):
        parser.error("--concept 必填真实概念（story 站必需），如 --concept \"雨夜便利店的神秘顾客\"")
    project = common.project_dir(args.artifacts_dir, args.project)

    # 本工作室无上游产物，无需 load_inputs
    caller = AgentCaller(demo_mode=args.demo, soul_dir=SOUL_DIR)
    artifact = build_artifact(args, {}, caller)

    manifest = common.load_manifest(project)
    common.mark_start(manifest, STUDIO_KEY, {})  # 无上游，血缘为空
    out_path = common.write_artifact(project, STUDIO_KEY, OUTPUT_FILE, artifact)
    common.mark_done(manifest, STUDIO_KEY, artifact)
    manifest.studios[STUDIO_KEY].cost_usd = caller.cost_usd()
    common.save_manifest(project, manifest)

    print(f"输出产物：{out_path}")
    print(f"项目台账：{project / 'manifest.json'}")
    print(f"本次 Agent 成本：${caller.cost_usd():.6f}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (common.InputError, common.HumanEditError, NoKeyError,
            JSONParseError, ValidationError, RuntimeError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)
