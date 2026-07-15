"""Core Bridge — 隔离层，唯一的入口。

OpenMontage 零侵入。调用走独立 worker 子进程，不 import 任何 OpenMontage 模块。
"""

from __future__ import annotations

import json
import os
import subprocess
import yaml
from pathlib import Path
from uuid import uuid4

from .models import (
    DiscoveryReport,
    ToolResult,
    PipelineInfo,
    PipelineStatus,
)
from .exceptions import (
    BridgeError,
    OpenMontageNotFound,
    OpenMontageNotSetup,
    PipelineError,
    DiscoveryError,
)

# ── 默认路径 ──────────────────────────────────────────────
# bridge.py → openmontage_bridge/ → openmontage-bridge/ → SceneCraft/
_BRIDGE_PKG = Path(__file__).resolve().parent.parent  # openmontage-bridge/
_PARENT = _BRIDGE_PKG.parent                          # SceneCraft/
_DEFAULT_OM_PATH = _PARENT / "OpenMontage"
_DEFAULT_OUTPUT_ROOT = _BRIDGE_PKG / "output"
_WORKER_SCRIPT = _BRIDGE_PKG / "scripts" / "worker.py"


class Bridge:
    """OpenMontage Bridge — 单一入口，隔离调用。

    所有 OpenMontage 操作通过独立子进程 (scripts/worker.py) 执行。
    Bridge 进程不 import 任何 OpenMontage Python 代码。
    """

    def __init__(
        self,
        openmontage_path: str | Path = _DEFAULT_OM_PATH,
        output_root: str | Path = _DEFAULT_OUTPUT_ROOT,
        python_exec: str | Path | None = None,
    ):
        self._om_root = self._resolve_om_path(openmontage_path)
        self._output_root = Path(output_root)
        self._output_root.mkdir(parents=True, exist_ok=True)
        self._python = self._resolve_python(python_exec)

        # 运行时状态 (discover 缓存)
        self._discovered = False
        self._last_summary: dict | None = None
        self._last_menu: dict | None = None
        self._last_support: dict | None = None
        self._all_tools: list[str] = []

    # ── 公开属性 ──────────────────────────────────────────

    @property
    def openmontage_root(self) -> Path:
        return self._om_root

    @property
    def output_root(self) -> Path:
        return self._output_root

    @property
    def python_path(self) -> str:
        return str(self._python)

    # ── 初始化 ─────────────────────────────────────────────

    def _resolve_om_path(self, path: str | Path) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = _PARENT / p
        p = p.resolve()
        if not (p / "tools" / "tool_registry.py").exists():
            raise OpenMontageNotFound(
                f"OpenMontage 未找到: {p}。"
            )
        return p

    def _resolve_python(self, override: str | Path | None) -> Path:
        if override:
            return Path(override)
        venv_python = self._om_root / ".venv" / "bin" / "python3"
        if venv_python.exists():
            return venv_python
        system = self._shutil_which("python3")
        if system:
            return Path(system)
        raise OpenMontageNotSetup(
            f"找不到 Python 解释器。"
            f"请先设置 OpenMontage 的 .venv: cd {self._om_root} && python3 -m venv .venv"
        )

    # ── 发现能力 ───────────────────────────────────────────

    def discover(self) -> DiscoveryReport:
        """执行 capability discovery，返回报告。"""
        data = self._call_worker("discover")

        self._last_summary = data["summary"]
        self._last_menu = None
        self._last_support = None
        self._all_tools = data["tools"]
        self._discovered = True

        s = data["summary"]
        return DiscoveryReport(
            composition_runtimes=s.get("composition_runtimes", {}),
            capabilities=s.get("capabilities", []),
            setup_offers=s.get("setup_offers", []),
            runtime_warnings=s.get("runtime_warnings", []),
            all_tool_names=data["tools"],
            project_root=str(self._om_root),
        )

    def _ensure_discovered(self):
        if not self._discovered:
            self.discover()

    def provider_menu_summary(self) -> dict:
        """获取 provider_menu_summary (N of M 菜单)。"""
        self._ensure_discovered()
        return self._last_summary

    def provider_menu(self) -> dict:
        """获取完整 provider_menu (含 install_instructions)。"""
        self._ensure_discovered()
        if self._last_menu is not None:
            return self._last_menu
        self._last_menu = self._call_worker("provider_menu")
        return self._last_menu

    def support_envelope(self) -> dict:
        """获取完整 support envelope (每个工具的完整信息)。"""
        self._ensure_discovered()
        if self._last_support is not None:
            return self._last_support
        self._last_support = self._call_worker("support_envelope")
        return self._last_support

    # ── 工具调用 ───────────────────────────────────────────

    def run_tool(
        self,
        tool_name: str,
        params: dict | None = None,
        timeout: int = 120,
    ) -> ToolResult:
        """调用单个 OpenMontage 工具。"""
        params = params or {}
        self._ensure_discovered()

        try:
            data = self._call_worker("run_tool", tool_name, params, timeout=timeout)
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"工具 {tool_name} 调用超时 ({timeout}s)",
                tool_name=tool_name,
            )

        cost = (
            data.get("data", {}).get("cost_usd", 0.0)
            if isinstance(data.get("data"), dict)
            else 0.0
        )
        return ToolResult(
            success=data.get("success", False),
            data=data.get("data"),
            error=data.get("error"),
            tool_name=tool_name,
            cost_usd=cost,
        )

    def list_tools(self) -> list[str]:
        """列出所有已注册工具名称。"""
        self._ensure_discovered()
        return self._all_tools

    def list_available_tools(self) -> list[str]:
        """列出当前可用的工具名称。"""
        self._ensure_discovered()
        return self._call_worker("list_available")

    def tool_info(self, tool_name: str) -> dict | None:
        """获取单个工具的详细信息。"""
        env = self.support_envelope()
        return env.get(tool_name)

    # ── 流水线 ─────────────────────────────────────────────

    def list_pipelines(self) -> list[PipelineInfo]:
        """列出所有可用的流水线 (读 YAML，不涉及 OpenMontage 模块)。"""
        pipeline_dir = self._om_root / "pipeline_defs"
        if not pipeline_dir.exists():
            return []

        pipelines: list[PipelineInfo] = []
        for yaml_file in sorted(pipeline_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                try:
                    manifest = yaml.safe_load(f)
                except Exception:
                    continue
                name = manifest.get("name", yaml_file.stem)
                stages = [s["name"] for s in manifest.get("stages", [])]
                gates = [s["name"] for s in manifest.get("stages", [])
                         if s.get("human_approval_default", False)]
                pipelines.append(PipelineInfo(
                    name=name,
                    description=manifest.get("description", ""),
                    stability=manifest.get("stability", "unknown"),
                    stages=stages,
                    human_approval_gates=gates,
                ))
        return pipelines

    def get_pipeline(self, name: str) -> PipelineInfo | None:
        """获取单条流水线的信息。"""
        for p in self.list_pipelines():
            if p.name == name:
                return p
        return None

    def init_pipeline_project(
        self,
        pipeline: str,
        project_id: str,
        title: str = "",
    ) -> Path:
        """初始化流水线项目目录。

        产物写到 bridge 的 output 目录，不污染 OpenMontage projects/。
        """
        project_dir = self._output_root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        # 通过 worker 调 OpenMontage 的 init_project
        self._call_worker("init_project", pipeline, project_id, title,
                          extra_env={"BASE_DIR": str(project_dir)})

        return project_dir

    # ── 高级 API：视频制作 ────────────────────────────────

    def make_video(
        self,
        prompt: str,
        pipeline: str = "animated-explainer",
        project_id: str | None = None,
        **kwargs,
    ) -> PipelineStatus:
        """一站式视频制作入口。"""
        pid = project_id or f"video-{uuid4().hex[:8]}"

        pipeline_info = self.get_pipeline(pipeline)
        if not pipeline_info:
            raise PipelineError(f"流水线不存在: {pipeline}")

        project_dir = self.init_pipeline_project(pipeline, pid, title=prompt[:60])

        return PipelineStatus(
            project_id=pid,
            pipeline_name=pipeline,
            current_stage="init",
            status="in_progress",
            artifacts={"prompt": prompt, "project_dir": str(project_dir)},
        )

    # ── 内部：worker 调用 ──────────────────────────────────

    def _call_worker(
        self,
        command: str,
        *args: str,
        timeout: int = 60,
        extra_env: dict | None = None,
    ) -> dict:
        """通过子进程调用 scripts/worker.py。

        Bridge 本身不 import 任何 OpenMontage 模块。
        Worker 在独立进程中加载 OpenMontage (AGPL)，是程序的"使用"而非"派生"。
        """
        cmd = [str(self._python), str(_WORKER_SCRIPT), command, *args]
        env = os.environ.copy()
        env["OM_ROOT"] = str(self._om_root)
        if extra_env:
            env.update(extra_env)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(self._om_root),
        )

        if proc.stderr and "Traceback" in proc.stderr:
            error_msg = proc.stderr[:500]
            if command == "discover":
                raise DiscoveryError(f"worker stderr: {error_msg}")
            raise BridgeError(f"worker error ({command}): {error_msg}")

        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise BridgeError(
                f"worker JSON 解析失败: {e}\nstdout={proc.stdout[:300]}"
            )

    @staticmethod
    def _shutil_which(cmd: str) -> str | None:
        import shutil
        return shutil.which(cmd)

    def __repr__(self) -> str:
        return (
            f"Bridge(om_root={self._om_root}, "
            f"python={self._python}, "
            f"discovered={self._discovered})"
        )
