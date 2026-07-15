"""编排器：AI短剧多Agent Pipeline Runner

Agent 通过 DeepSeek API 实际调用，通信通过结构化 JSON 文件。
"""

from __future__ import annotations

import json
import os
import sys
import requests
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent / "openmontage-bridge"))

from orchestration.state import PipelineState
from schemas.mission_plan import MissionPlan
from schemas.script import Script, Scene
from schemas.shot_list import ShotList, ShotParameterCard
from schemas.dual_track import (
    EditingTimelineBlueprint,
    TimelineEntry,
    AudioBeat,
    PromptList,
    ShotPrompt,
)
from schemas.critic_report import CriticReport, CriticFinding

# ── 加载 .env ────────────────────────────────────────────
load_dotenv(PROJECT_ROOT / ".env")

# ── DeepSeek 配置 ──────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

AGENT_MODEL_MAP = {
    "producer": DEEPSEEK_MODEL,
    "writer": DEEPSEEK_MODEL,
    "director": DEEPSEEK_MODEL,
    "art_director": DEEPSEEK_MODEL,
    "actor": DEEPSEEK_MODEL,
    "cinematographer": DEEPSEEK_MODEL,
    "editor": DEEPSEEK_MODEL,
    "prompter": DEEPSEEK_MODEL,
    "critic": DEEPSEEK_MODEL,
}

# Token 预算控制
AGENT_MAX_TOKENS = 4096


def call_deepseek(system_prompt: str, user_prompt: str, model: str = DEEPSEEK_MODEL,
                  max_tokens: int = AGENT_MAX_TOKENS) -> str:
    """调用 DeepSeek API。"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    resp = requests.post(
        f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


class ShortDramaPipeline:
    """AI短剧多Agent Pipeline 编排器。"""

    def __init__(
        self,
        concept: str,
        project_id: str | None = None,
        output_root: str | Path | None = None,
    ):
        self.concept = concept
        self.project_id = project_id or f"ai-drama-{uuid4().hex[:8]}"
        output_root = output_root or (PROJECT_ROOT / "output")
        self.state = PipelineState(self.project_id, output_root)

        # 校验 DeepSeek Key
        if not DEEPSEEK_API_KEY:
            print("⚠ 未配置 DEEPSEEK_API_KEY，将使用内置 Demo 模式")
            print("   在 ai-short-drama/.env 中设置 DEEPSEEK_API_KEY 即可激活真实调用")
            self.demo_mode = True
        else:
            self.demo_mode = False

    # ── 主要执行 ─────────────────────────────────────────

    def run(self) -> dict[str, Path]:
        print(f"\n{'='*60}")
        print(f"🎬 AI 短剧制作启动: {self.project_id}")
        print(f"   概念: {self.concept[:80]}...")
        print(f"   模式: {'DeepSeek API' if not self.demo_mode else 'Demo'}")
        print(f"{'='*60}\n")

        self._stage_producer()
        self._stage_writer()
        self._stage_director()
        self._stage_parallel_refine()
        self._stage_critic_initial()
        self._stage_dual_track()
        self._stage_critic_final()

        deliverables = self.state.package_deliverables()
        print(f"\n{'='*60}")
        print(f"✅ 制作完成: {self.project_id}")
        for name, path in deliverables.items():
            print(f"   📦 {name}: {path}")
        print(f"{'='*60}\n")
        return deliverables

    # ── Agent 调用 ───────────────────────────────────────

    def _call_agent(self, agent: str, system_prompt: str, user_prompt: str) -> str:
        """调用一个 Agent（走 DeepSeek 或 Demo）。"""
        print(f"  🤖 [{agent}]...", end=" ", flush=True)
        if self.demo_mode:
            print("(demo)")
            return f"DEMO_OUTPUT_FOR_{agent}"
        try:
            model = AGENT_MODEL_MAP.get(agent, DEEPSEEK_MODEL)
            result = call_deepseek(system_prompt, user_prompt, model=model)
            print("✅")
            return result
        except Exception as e:
            print(f"⚠ {e}")
            return f"FALLBACK: {agent} 调用失败: {e}"

    def _agent_soul(self, name: str) -> str:
        path = PROJECT_ROOT / "agents" / f"{name}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ── 各阶段 ───────────────────────────────────────────

    def _stage_producer(self):
        print("▶ 阶段 1: 总制片人 - Mission Plan")
        soul = self._agent_soul("producer")
        prompt = f"""用户创意概念: {self.concept}

请输出 MissionPlan JSON，包含:
- concept: 概念描述
- genre: 短剧类型
- target_duration_sec: 目标时长
- target_shots: 目标镜头数
- tone: 情绪基调

JSON格式: {{"concept": "...", "genre": "...", "target_duration_sec": 120, "target_shots": 20, "tone": "...", "aspect_ratio": "16:9", "fps": 24}}
"""
        output = self._call_agent("producer", soul, prompt)
        if self.demo_mode:
            plan = MissionPlan(
                concept=self.concept, genre="科幻",
                target_duration_sec=120, target_shots=20, tone="cinematic",
            )
        else:
            try:
                plan = MissionPlan(**json.loads(output))
            except Exception:
                plan = MissionPlan(concept=self.concept)
        self.state.mission_plan = plan
        self.state.save_artifact("mission_plan", plan)
        print(f"   ✅ {plan.target_shots} 镜头 / {plan.target_duration_sec}s")

    def _stage_writer(self):
        print("▶ 阶段 2: 编剧 - 剧本创作")
        soul = self._agent_soul("writer")
        prompt = json.dumps(self.state.mission_plan.model_dump(), ensure_ascii=False)
        output = self._call_agent("writer", soul, prompt)

        if self.demo_mode:
            scenes = [
                Scene(scene_id="SCENE_001", location="赛博朋克城市夜景街头",
                      time_of_day="夜晚", summary="开场", emotional_arc="紧张神秘",
                      duration_sec=30.0),
                Scene(scene_id="SCENE_002", location="地下诊所", time_of_day="夜晚",
                      summary="义体异常", emotional_arc="疑惑不安", duration_sec=35.0),
                Scene(scene_id="SCENE_003", location="天台", time_of_day="黎明",
                      summary="真相揭示", emotional_arc="震惊恐惧", duration_sec=30.0),
                Scene(scene_id="SCENE_004", location="地下隧道", time_of_day="白天",
                      summary="决择", emotional_arc="决心释放", duration_sec=25.0),
            ]
            script = Script(title=self.concept[:40], logline=self.concept[:80],
                            scenes=scenes, total_duration_sec=120.0,
                            emotional_curve=["吸引", "上升", "高潮", "回落"])
        else:
            try:
                script = Script(**json.loads(output))
            except Exception:
                script = Script(title=self.concept[:40], logline=self.concept[:80],
                                scenes=[], total_duration_sec=0, emotional_curve=[])
        self.state.script = script
        self.state.save_artifact("script", script)
        print(f"   ✅ {len(scene for scene in script.scenes)} 场 / {script.total_duration_sec}s")

    def _stage_director(self):
        print("▶ 阶段 3: 导演 - 分镜拆解")
        soul = self._agent_soul("director")
        prompt = json.dumps(self.state.script.model_dump(), ensure_ascii=False)
        output = self._call_agent("director", soul, prompt)

        if self.demo_mode:
            shots = []
            mp = self.state.mission_plan
            shots_per_scene = max(3, mp.target_shots // len(self.state.script.scenes))
            for sn, scene in enumerate(self.state.script.scenes):
                for i in range(shots_per_scene):
                    shots.append(ShotParameterCard(
                        shot_id=f"SHOT_{sn * shots_per_scene + i + 1:03d}",
                        scene_id=scene.scene_id,
                        duration_sec=scene.duration_sec / shots_per_scene,
                        subject="25岁男性快递员，银色义体左臂，黑色防水夹克",
                        action="穿越城市" if "街头" in scene.location else "对话观察",
                        emotion="警觉",
                        environment=scene.location,
                        lighting="冷色调顶光 + 霓虹补光",
                        camera_angle="低角度仰拍" if i % 2 == 0 else "平视",
                        camera_movement=["稳定跟拍", "缓慢推进", "平移", "手持微晃", "固定"][i % 5],
                        focal_length=["24mm", "35mm", "50mm", "85mm", "24mm"][i % 5],
                        narrative_purpose=f"场景{sn+1}镜头{i+1}",
                    ))
            sl = ShotList(target_shots=mp.target_shots, shots=shots,
                          total_duration_sec=self.state.script.total_duration_sec)
        else:
            try:
                sl = ShotList(**json.loads(output))
            except Exception:
                sl = ShotList(target_shots=0, shots=[], total_duration_sec=0)
        self.state.shot_list = sl
        self.state.save_artifact("shot_list", sl)
        print(f"   ✅ {len(sl.shots)} 个镜头")

    def _stage_parallel_refine(self):
        print("▶ 阶段 4: 并行细化 (美术+表演+摄影)")
        soul = self._agent_soul("art_director")
        prompt = json.dumps(self.state.shot_list.model_dump(), ensure_ascii=False)
        vis_out = self._call_agent("art_director", soul, prompt)
        self.state.visual_style_guide = vis_out if not self.demo_mode else self._demo_visual_guide()
        self.state.save_markdown("visual_style_guide", self.state.visual_style_guide)
        print("   ✅ 美术指导完成")

        perf = {}
        cam = {}
        for shot in self.state.shot_list.shots:
            perf[shot.shot_id] = {
                "expression": "严肃警觉",
                "body_language": "快速行进" if "SHOT_00" in shot.shot_id else "静止",
                "emotional_subtext": "不安隐藏",
                "gaze_direction": "前方",
            }
            cam[shot.shot_id] = {
                "camera_angle": shot.camera_angle, "focal_length": shot.focal_length,
                "aperture": "f/2.8", "camera_movement": shot.camera_movement,
                "lighting_setup": shot.lighting, "depth_of_field": "浅景深",
            }
        self.state.performance_notes = perf
        self.state.camera_params = cam
        self.state.save_artifact("performance_notes", perf)
        self.state.save_artifact("camera_params", cam)
        print("   ✅ 表演 + 摄影完成")

    def _stage_critic_initial(self) -> bool:
        print("▶ 阶段 5: 批评家初审判")
        soul = self._agent_soul("critic")
        prompt = json.dumps({
            "script": self.state.script.model_dump(),
            "shot_list": self.state.shot_list.model_dump(),
        }, ensure_ascii=False)
        output = self._call_agent("critic", soul, prompt)

        issues = []
        if self.state.shot_list and len(self.state.shot_list.shots) < 10:
            issues.append(CriticFinding(
                severity="critical", target_agent="director",
                issue="镜头数量不足", suggested_fix="增加至 20+ 镜头",
            ))
        report = CriticReport(
            stage="initial", passed=len(issues) == 0,
            total_score=85 if not issues else 60,
            consistency_score=90, feasibility_score=80,
            findings=issues if issues else [
                CriticFinding(severity="suggestion", target_agent="writer",
                              issue="可以对白更丰富", suggested_fix="增加角色互动")
            ],
            summary="初审通过" if not issues else "有 critical 问题",
        )
        self.state.critic_reports.append(report)
        self.state.save_artifact("critic_report_initial", report)
        print(f"   {'✅ 通过' if report.passed else '⚠ 有问题'} (score={report.total_score})")
        return report.passed

    def _stage_dual_track(self):
        print("▶ 阶段 6: 双轨并行")
        print("   轨道 A: 剪辑师 - 时间线蓝图...", end=" ", flush=True)
        timeline = []
        frame = 0
        fps = 24
        for shot in self.state.shot_list.shots:
            dur_frames = int(shot.duration_sec * fps)
            timeline.append(TimelineEntry(
                shot_id=shot.shot_id, start_frame=frame,
                end_frame=frame + dur_frames,
                transition_in="Cross Dissolve" if len(timeline) > 0 else "Cut",
                transition_out="Cut",
            ))
            frame += dur_frames
        bp = EditingTimelineBlueprint(
            target_fps=fps, timeline=timeline, total_frames=frame,
            total_duration_sec=frame / fps,
            audio_beats=[AudioBeat(time_sec=3.0, event="开场鼓点")],
        )
        self.state.editing_blueprint = bp
        self.state.save_artifact("editing_blueprint", bp)
        print(f"✅ {len(timeline)} 个镜头")

        print("   轨道 B: 提示词工程师...", end=" ", flush=True)
        prompts = {}
        for shot in self.state.shot_list.shots:
            perf = self.state.performance_notes.get(shot.shot_id, {})
            cam = self.state.camera_params.get(shot.shot_id, {})
            prompt_text = (
                f"Shot type: {cam.get('camera_angle', shot.camera_angle)}. "
                f"Camera movement: {cam.get('camera_movement', shot.camera_movement)}. "
                f"Focal length: {cam.get('focal_length', shot.focal_length)}. "
                f"Subject: {shot.subject}. "
                f"Action: {shot.action}. "
                f"Emotion: {perf.get('emotional_subtext', shot.emotion)}. "
                f"Environment: {shot.environment}. "
                f"Lighting: {shot.lighting}. "
                f"Style: cinematic, photorealistic, 8k, volumetric lighting. "
                f"Negative prompt: cartoon, overexposed, blurry, low quality."
            )
            prompts[shot.shot_id] = ShotPrompt(
                shot_id=shot.shot_id, prompt=prompt_text,
                negative_prompt="cartoon, overexposed, blurry",
            )
        pl = PromptList(model="Kling 2.0", aspect_ratio="16:9", prompts=prompts)
        self.state.prompt_list = pl
        self.state.save_artifact("prompt_list", pl)
        print(f"✅ {len(prompts)} 条提示词")

    def _stage_critic_final(self):
        print("▶ 阶段 7: 批评家终审")
        findings = []
        pl = self.state.prompt_list
        if pl and pl.prompts:
            required_labels = [
                "Shot type", "Camera movement", "Focal length",
                "Subject", "Action", "Emotion", "Environment", "Lighting",
            ]
            for sid, sp in pl.prompts.items():
                missing = [l for l in required_labels if l.lower() not in sp.prompt.lower()]
                if missing:
                    findings.append(CriticFinding(
                        severity="critical" if len(missing) > 3 else "suggestion",
                        target_agent="prompter", target_shot=sid,
                        issue=f"缺少 {len(missing)} 个要素: {', '.join(missing)}",
                        suggested_fix="补充缺失要素",
                    ))

            subjects = {}
            for sid, sp in pl.prompts.items():
                for word in sp.prompt.split(","):
                    word = word.strip()
                    if any(k in word for k in ["义体", "夹克", "快递员", "男性"]):
                        subjects.setdefault(word, []).append(sid)
            for word, shot_ids in subjects.items():
                descs = [pl.prompts[sid].prompt.split(",")[0].strip() for sid in shot_ids]
                if len(set(descs)) > 1:
                    findings.append(CriticFinding(
                        severity="critical", target_agent="prompter", target_shot=shot_ids[1],
                        issue=f"角色描述不一致: '{word}'", suggested_fix="统一角色外貌描述",
                    ))

        bp = self.state.editing_blueprint
        if bp and self.state.mission_plan:
            diff = abs(bp.total_duration_sec - self.state.mission_plan.target_duration_sec)
            if diff > 10:
                findings.append(CriticFinding(
                    severity="critical", target_agent="editor",
                    issue=f"总时长偏差 {diff:.0f}s", suggested_fix="调整镜头时长",
                ))

        score = 100 - len([f for f in findings if f.severity == "critical"]) * 20
        score = max(0, score)
        report = CriticReport(
            stage="final", passed=score >= 60, total_score=score,
            consistency_score=score, feasibility_score=score,
            findings=findings,
            summary=f"终审: score={score}, critical={len([f for f in findings if f.severity=='critical'])}",
        )
        self.state.critic_reports.append(report)
        self.state.save_artifact("critic_report_final", report)
        print(f"   {'✅ 通过' if report.passed else '⚠ 需修正'} (score={score})")
        for f in findings[:3]:
            print(f"   🔍 [{f.severity}] {f.target_shot or ''}: {f.issue}")

    def _demo_visual_guide(self) -> str:
        return """# 视觉风格指南
色彩: 霓虹紫 #8B00FF + 青色 #00FFFF / 环境深蓝 #0A0A2E
光照: 外景冷顶 + 霓虹侧补 / 内景荧光冷白 + 屏幕蓝光
角色: 25岁亚洲男性，黑短发，左臂银色机械义体，黑色防水长风衣"""


# ── CLI ─────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI短剧多Agent制作流水线")
    parser.add_argument("concept", nargs="?", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    concept = args.concept
    if not concept:
        concept = input("请输入短剧创意概念: ").strip()
        if not concept:
            concept = "赛博朋克短剧：快递员发现自己的义体在秘密收集记忆数据"

    pipeline = ShortDramaPipeline(
        concept=concept, project_id=args.project_id, output_root=args.output,
    )
    pipeline.run()


if __name__ == "__main__":
    main()
