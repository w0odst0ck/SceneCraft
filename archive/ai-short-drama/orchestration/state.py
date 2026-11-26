"""编排器核心：多 Agent Pipeline 状态管理"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from schemas.mission_plan import MissionPlan
from schemas.script import Script
from schemas.shot_list import ShotList, ShotParameterCard
from schemas.dual_track import (
    EditingTimelineBlueprint,
    PromptList,
    ShotPrompt,
)
from schemas.critic_report import CriticReport, CriticFinding


class PipelineState:
    """单次短剧任务的全状态管理。"""

    def __init__(self, project_id: str, output_root: str | Path):
        self.project_id = project_id
        self.output_dir = Path(output_root) / project_id
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 各阶段产物
        self.mission_plan: Optional[MissionPlan] = None
        self.script: Optional[Script] = None
        self.shot_list: Optional[ShotList] = None
        self.visual_style_guide: Optional[str] = None
        self.performance_notes: Optional[dict] = None
        self.camera_params: Optional[dict] = None
        self.editing_blueprint: Optional[EditingTimelineBlueprint] = None
        self.prompt_list: Optional[PromptList] = None
        self.critic_reports: list[CriticReport] = []

        # 迭代计数
        self.iteration = 0
        self.max_iterations = 3

    # ── 持久化 ───────────────────────────────────────────

    def save_artifact(self, name: str, data: Any):
        path = self.output_dir / f"{name}.json"
        if isinstance(data, BaseModel):
            path.write_text(data.model_dump_json(indent=2))
        else:
            path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        return path

    def save_markdown(self, name: str, content: str):
        path = self.output_dir / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def load_artifact(self, name: str) -> dict:
        path = self.output_dir / f"{name}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    # ── 阶段推进 ─────────────────────────────────────────

    def stage_name(self) -> str:
        if self.mission_plan is None:
            return "producer_init"
        if self.script is None:
            return "writer"
        if self.shot_list is None:
            return "director"
        if self.visual_style_guide is None or self.performance_notes is None or self.camera_params is None:
            return "parallel_refine"  # art_director + actor + cinematographer
        if not self._critic_passed("initial"):
            return "critic_initial"
        if self.prompt_list is None or self.editing_blueprint is None:
            return "dual_track"  # prompter + editor (并行)
        if not self._critic_passed("final"):
            return "critic_final"
        return "complete"

    def _critic_passed(self, stage: str) -> bool:
        for r in self.critic_reports:
            if r.stage == stage and r.passed:
                return True
        return False

    # ── 交付打包 ─────────────────────────────────────────

    def package_deliverables(self) -> dict[str, Path]:
        """打包最终交付物。"""
        package = {}
        # 核心交付物 1: 提示词列表
        pl_path = self.output_dir / "prompts_for_ai_video.json"
        if self.prompt_list:
            pl_path.write_text(self.prompt_list.model_dump_json(indent=2, ensure_ascii=False))
            package["prompts_for_ai_video"] = pl_path

        # 核心交付物 2: 剪辑蓝图 (同时输出 EDL 兼容 + JSON)
        bp_path = self.output_dir / "editing_blueprint.json"
        if self.editing_blueprint:
            bp_path.write_text(self.editing_blueprint.model_dump_json(indent=2))
            package["editing_blueprint"] = bp_path

        # 交付物 3: 元数据
        meta = self._build_metadata()
        meta_path = self.output_dir / "project_metadata.txt"
        meta_path.write_text(meta, encoding="utf-8")
        package["project_metadata"] = meta_path

        # 交付物 4: 质检报告
        if self.critic_reports:
            report_path = self.output_dir / "production_report.json"
            reports_json = [r.model_dump() for r in self.critic_reports]
            report_path.write_text(json.dumps(reports_json, indent=2, ensure_ascii=False))
            package["production_report"] = report_path

        return package

    def _build_metadata(self) -> str:
        lines = [
            f"项目: {self.project_id}",
            f"生成时间: {datetime.now().isoformat()}",
            f"总时长: {self.editing_blueprint.total_duration_sec if self.editing_blueprint else 'N/A'} 秒",
            f"推荐帧率: {self.editing_blueprint.target_fps if self.editing_blueprint else 24} fps",
            f"画幅比例: {self.mission_plan.aspect_ratio if self.mission_plan else '16:9'}",
            f"镜头数: {len(self.shot_list.shots) if self.shot_list else 0}",
            f"迭代轮次: {self.iteration}",
            "",
            "情绪关键时间节点:",
        ]
        if self.script:
            for scene in self.script.scenes:
                lines.append(f"  {scene.scene_id}: {scene.emotional_arc} @ ~{scene.duration_sec}s")
        return "\n".join(lines)


from pydantic import BaseModel
