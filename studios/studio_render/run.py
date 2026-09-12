"""Studio Render — 渲染站

默认（降级实现）：本任务只出渲染计划，不做真实渲染。
输入产物：04_prompt/prompt_list.json（PromptList）+ 05_edit/editing_blueprint.json（EditingBlueprint）
实现：聚合 prompt_list + editing_blueprint → RenderPlan
  - 每镜头一条渲染任务卡（provider 默认 "openmontage-pending"、status "pending"）
  - estimated_cost_usd 按镜头时长粗估（常量 COST_PER_SEC_USD）
输出产物：<artifacts>/<project_id>/06_render/render_plan.json
  （契约 schemas/render_plan.py::RenderPlan）

--render（S4 接入真实本地渲染）：ComfyUI + LTX-Video 2B 逐镜串行出片
  1) 渲染前卸载 ollama（显存纪律，12GB 卡须独占 GPU）
  2) 逐镜：任务卡 prompt + 固定 negative → 构造 LTXV workflow → 提交 → 轮询 → 下载
     → <artifacts>/<project_id>/06_render/<shot_id>.webm
     → 回填 status=done / output_file / duration_sec / peak_vram_mb / provider="comfyui-ltxv"
  3) 单镜失败重试 1 次；仍失败则 status=failed + error（不静默），继续下一镜（不整体中止）
  4) 渲染后写回 render_plan.json；manifest 正常记 cost=0（本地渲染无 API 费用）
  --render-limit N 只渲前 N 镜（其余保持 pending），便于快速验证
  width/height/length/steps/cfg/fps/ckpt 等用常量默认，可用 SCENE_RENDER_* 环境变量覆盖；
  ComfyUI 地址与产物目录沿用 comfyui_video 的 SCENE_COMFY_* 环境变量

manifest key：render ↔ 磁盘目录 06_render（映射见 SKILL.md）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# LTX 渲染客户端在 scripts/ 下（无包结构），按脚本目录直接 import
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import time  # noqa: E402

try:
    import comfyui_video  # noqa: E402  （scripts/comfyui_video.py：LTX 客户端）
except ImportError:  # 仅在 --render 时需要；缺失时默认（只出计划）路径不受影响
    comfyui_video = None  # type: ignore[assignment]

from schemas.editing_blueprint import EditingBlueprint  # noqa: E402
from schemas.prompt_list import PromptList  # noqa: E402
from schemas.render_plan import RenderPlan, RenderShot  # noqa: E402
from studios import common  # noqa: E402
from studios.agent_utils import NoKeyError  # noqa: E402

STUDIO_KEY = "render"
OUTPUT_FILE = "render_plan.json"
INPUTS: list[tuple[str, str, type]] = [
    ("prompt", "prompt_list.json", PromptList),
    ("edit", "editing_blueprint.json", EditingBlueprint),
]

# 渲染成本粗估：按镜头时长 × 单价（美元/秒，示例值，Phase D 按实际服务商计价修正）
COST_PER_SEC_USD = 0.003

RENDER_NOTES = (
    "默认（无 --render）为渲染计划占位：shots 逐镜 status=pending、provider=openmontage-pending。"
    "运行 --render 后由本地 ComfyUI + LTX-Video 2B 逐镜出片，完成镜 provider=comfyui-ltxv、"
    "status=done 并回填 output_file/duration_sec/peak_vram_mb；失败镜 status=failed + error。"
)

# ── 真实渲染默认参数（LTX-Video 2B v0.9.5 已验档：1024x576 · 30 步 · cfg 3.0 · fps 25）──
# 全部可用 SCENE_RENDER_* 环境变量覆盖（便于换卡/换分辨率/换模型，不改代码）
PROVIDER_COMFYUI = "comfyui-ltxv"
RENDER_RETRIES = 1          # 单镜失败重试次数（共尝试 1 + RENDER_RETRIES 次）
DEFAULT_PROMPT_FALLBACK = "cinematic film scene, natural motion, consistent lighting"  # 任务卡无 prompt 时兜底
def _env_value(name: str, default: str) -> str:
    """读字符串环境变量；缺失则用默认值。"""
    value = os.environ.get(name)
    return value if value else default


def _env_int(name: str, default: int) -> int:
    """读整型环境变量；缺失或非法则用默认值（不抛异常，避免环境噪声打断渲染）。"""
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    """读浮点环境变量；缺失或非法则用默认值。"""
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def render_params(cv: Any = None) -> dict[str, Any]:
    """真实渲染参数：常量默认 + SCENE_RENDER_* 环境变量覆盖（每次调用现读环境）。

    地址/产物目录沿用客户端自身的 SCENE_COMFY_* 环境变量（comfyui_video 模块常量），
    避免同一含义出现两套环境变量名。
    """
    cv = cv or comfyui_video
    return {
        "width": _env_int("SCENE_RENDER_WIDTH", cv.DEFAULT_WIDTH),
        "height": _env_int("SCENE_RENDER_HEIGHT", cv.DEFAULT_HEIGHT),
        "length": _env_int("SCENE_RENDER_LENGTH", cv.DEFAULT_LENGTH),
        "steps": _env_int("SCENE_RENDER_STEPS", cv.DEFAULT_STEPS),
        "cfg": _env_float("SCENE_RENDER_CFG", cv.DEFAULT_CFG),
        "fps": _env_float("SCENE_RENDER_FPS", cv.DEFAULT_FPS),
        "seed": _env_int("SCENE_RENDER_SEED", cv.DEFAULT_SEED),
        "ckpt": _env_value("SCENE_RENDER_CKPT", cv.DEFAULT_CKPT),
        "negative": _env_value("SCENE_RENDER_NEGATIVE", cv.DEFAULT_NEGATIVE),
        "base_url": cv.DEFAULT_BASE_URL,
        "comfy_output": cv.DEFAULT_COMFY_OUTPUT,
        "poll": _env_float("SCENE_RENDER_POLL", cv.DEFAULT_POLL),
        "max_wait": _env_float("SCENE_RENDER_MAX_WAIT", cv.DEFAULT_MAX_WAIT),
        # 卸载 ollama 后等待显存真正释放（已验证 spike 的显存纪律）
        "unload_wait": _env_float("SCENE_RENDER_UNLOAD_WAIT", 3.0),
    }


def build_artifact(args: Any, inputs: dict[str, Any]) -> RenderPlan:
    """聚合 prompt_list + editing_blueprint → RenderPlan（降级实现，无 Agent 调用）。"""
    prompt_list: PromptList = inputs["prompt"]  # type: ignore[assignment]
    edit_bp: EditingBlueprint = inputs["edit"]  # type: ignore[assignment]
    fps = edit_bp.target_fps or 24

    shots: list[RenderShot] = []
    for entry in edit_bp.timeline:
        # 帧号闭区间语义（含端点）：镜长 = end - start + 1
        duration = max(0.0, (entry.end_frame - entry.start_frame + 1) / fps)
        sp = prompt_list.prompts.get(entry.shot_id)
        shots.append(RenderShot(
            shot_id=entry.shot_id,
            provider="openmontage-pending",
            prompt=sp.prompt if sp else "",
            estimated_cost_usd=round(duration * COST_PER_SEC_USD, 4),
            status="pending",
        ))
    total = round(sum(s.estimated_cost_usd for s in shots), 4)
    return RenderPlan(
        project_id=args.project,
        shots=shots,
        total_estimated_cost_usd=total,
        notes=RENDER_NOTES,
    )


def _relpath(path: Path, artifacts_dir: str | Path) -> str:
    """产物相对 artifacts 根目录的路径（POSIX 风格）；不在根下时退回绝对路径。"""
    try:
        return path.resolve().relative_to(Path(artifacts_dir).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _render_one(shot: RenderShot, out_dir: Path, params: dict[str, Any],
                artifacts_dir: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    """渲染单镜：失败重试 RENDER_RETRIES 次。成功返回 (统计, None)，失败返回 (None, 错误)。"""
    last_err: str | None = None
    for attempt in range(1, RENDER_RETRIES + 2):
        if attempt > 1:
            print(f"      ↻ 重试 {attempt - 1}/{RENDER_RETRIES}…")
        try:
            workflow = comfyui_video.build_ltxv_workflow(
                prompt=shot.prompt or DEFAULT_PROMPT_FALLBACK,
                negative=params["negative"],
                width=params["width"], height=params["height"], length=params["length"],
                steps=params["steps"], cfg=params["cfg"], seed=params["seed"],
                fps=params["fps"], ckpt=params["ckpt"],
            )
            prompt_id = comfyui_video.submit(params["base_url"], workflow)
            files = comfyui_video.wait_and_download(
                params["base_url"], prompt_id, out_dir,
                poll=params["poll"], max_wait=params["max_wait"],
                target_stem=shot.shot_id, comfy_output=params["comfy_output"],
            )
            run = comfyui_video.last_run()
            peak = run.get("peak_vram_mb")
            return {
                "output_file": _relpath(Path(files[0]), artifacts_dir),
                "duration_sec": round(params["length"] / max(params["fps"], 1e-6), 3),
                "peak_vram_mb": peak if isinstance(peak, int) and peak >= 0 else None,
            }, None
        except Exception as exc:  # noqa: BLE001 - 单镜任何异常都收敛为失败态，不中断整体
            last_err = f"{type(exc).__name__}: {exc}"
    return None, last_err


def render_shots(artifact: RenderPlan, project: Path, artifacts_dir: str | Path,
                 limit: int | None = None) -> tuple[int, int]:
    """串行真实渲染：逐镜出片并就地回填 RenderShot，返回 (成功镜数, 尝试镜数)。

    单镜失败重试 1 次后置 status=failed + error，继续下一镜（不整体中止）。
    limit 给定时只渲前 limit 镜，其余保持 pending。
    """
    if comfyui_video is None:
        raise RuntimeError(
            "--render 需要 scripts/comfyui_video.py（LTX 渲染客户端），但未能导入该模块；"
            "请检查仓库完整性（默认只出渲染计划的路径不依赖它）。")
    params = render_params()
    out_dir = project / common.STAGE_DIRS[STUDIO_KEY]
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = artifact.shots[:limit] if limit and limit > 0 else artifact.shots

    print(f"🎬 真实渲染（LTX-Video 2B）：{len(shots)}/{len(artifact.shots)} 镜 · "
          f"{params['width']}x{params['height']} · {params['length']} 帧 · {params['steps']} 步 · "
          f"cfg {params['cfg']} · ckpt {params['ckpt']}")
    # 显存纪律：渲染前卸载 ollama（12GB 卡须独占 GPU）
    freed = comfyui_video.unload_ollama()
    print(f"   已卸载 ollama 模型 {freed or '（无）'}｜当前显存 {comfyui_video.gpu_mb()} MiB")
    if params["unload_wait"] > 0:
        time.sleep(params["unload_wait"])  # 等显存真正释放（spike 已验证），避免首镜 OOM

    ok_count = 0
    for idx, shot in enumerate(shots, 1):
        print(f"   ▶ [{idx}/{len(shots)}] {shot.shot_id} 渲染中…")
        stats, err = _render_one(shot, out_dir, params, artifacts_dir)
        if stats is None:
            shot.status = "failed"
            shot.provider = PROVIDER_COMFYUI  # 已实际提交过真实渲染（区别于从未渲染）
            shot.error = err
            print(f"   ✗ {shot.shot_id} 渲染失败：{err}")
            continue
        shot.status = "done"
        shot.provider = PROVIDER_COMFYUI
        shot.output_file = stats["output_file"]
        shot.duration_sec = stats["duration_sec"]
        shot.peak_vram_mb = stats["peak_vram_mb"]
        shot.error = None
        ok_count += 1
        peak_txt = (f"{stats['peak_vram_mb']} MiB" if stats["peak_vram_mb"] is not None
                    else "未知（nvidia-smi 不可用）")
        print(f"   ✓ {shot.shot_id} 完成 {stats['duration_sec']:.1f}s "
              f"峰值 {peak_txt} → {stats['output_file']}")

    failed = len(shots) - ok_count
    tail = f"，失败 {failed} 镜（原因见 render_plan.json 的 error 字段）" if failed else ""
    print(f"渲染汇总：成功 {ok_count}/{len(shots)} 镜{tail}")
    return ok_count, len(shots)


def main(argv: list[str] | None = None) -> int:
    parser = common.build_parser(
        "Studio Render：渲染站（默认只出渲染计划；--render 接真实本地渲染）")
    parser.add_argument("--render", action="store_true",
                        help="真实本地渲染（ComfyUI + LTX-Video 2B），逐镜串行出 06_render/*.webm")
    parser.add_argument("--render-limit", type=int, default=None,
                        help="仅渲染前 N 镜（其余保持 pending，便于快速验证）；仅 --render 时生效")
    args = parser.parse_args(argv)
    if args.render_limit is not None and args.render_limit <= 0:
        parser.error("--render-limit 必须为正整数")
    if args.render_limit is not None and not args.render:
        print("提示：--render-limit 仅配合 --render 生效，本次忽略。")

    project = common.project_dir(args.artifacts_dir, args.project)

    # 加载输入产物（缺 prompt_list / editing_blueprint 时友好报错，提示先跑上游）
    inputs = common.load_inputs(project, INPUTS)

    artifact = build_artifact(args, inputs)

    # 真实渲染：写盘前完成回填，产物与 manifest 状态一致
    if args.render:
        render_shots(artifact, project, args.artifacts_dir, args.render_limit)

    manifest = common.load_manifest(project)
    common.mark_start(manifest, STUDIO_KEY, common.upstream_hashes(inputs))
    out_path = common.write_artifact(project, STUDIO_KEY, OUTPUT_FILE, artifact)
    common.mark_done(manifest, STUDIO_KEY, artifact)
    manifest.studios[STUDIO_KEY].cost_usd = 0.0  # 本地渲染，无 API 成本
    common.save_manifest(project, manifest)

    print(f"输出产物：{out_path}")
    print(f"项目台账：{project / 'manifest.json'}")
    print(f"渲染计划：{len(artifact.shots)} 镜 / 预估成本 ${artifact.total_estimated_cost_usd:.4f}")
    if args.render:
        done = sum(1 for s in artifact.shots if s.status == "done")
        failed = sum(1 for s in artifact.shots if s.status == "failed")
        print(f"渲染状态：done {done} / failed {failed} / pending "
              f"{len(artifact.shots) - done - failed}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (common.InputError, common.HumanEditError, NoKeyError,
            ValidationError, RuntimeError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)
