#!/usr/bin/env python3
"""Bridge Worker — 隔离执行入口。

openmontage-bridge (MIT) 通过 subprocess 调此脚本。
此脚本是唯一 import OpenMontage (AGPL) 模块的地方，以独立进程运行。
"""

import json
import os
import sys
from pathlib import Path


# ── 路径注入 ──────────────────────────────────────────────
# OpenMontage 根目录通过 ENV 或 CWD 传入
om_root = os.environ.get("OM_ROOT") or os.getcwd()
sys.path.insert(0, str(om_root))

from tools.tool_registry import registry


# ── 命令集 ────────────────────────────────────────────────

def cmd_discover() -> dict:
    registry.discover()
    return {
        "summary": registry.provider_menu_summary(),
        "tools": registry.list_all(),
    }


def cmd_provider_menu() -> dict:
    registry.discover()
    return registry.provider_menu()


def cmd_support_envelope() -> dict:
    registry.discover()
    return registry.support_envelope()


def cmd_list_available() -> list:
    registry.discover()
    return [t.name for t in registry.get_available()]


def cmd_run_tool(tool_name: str, params: dict) -> dict:
    registry.discover()
    tool = registry.get(tool_name)
    if tool is None:
        return {"success": False, "error": f"Tool not found: {tool_name}"}
    result = tool.execute(params)
    return {
        "success": result.success,
        "data": result.data,
        "error": result.error,
    }


def cmd_init_project(pipeline: str, project_id: str, title: str) -> dict:
    from lib.checkpoint import init_project
    base_dir = os.environ.get("BASE_DIR")
    result = init_project(
        project_id=project_id,
        title=title,
        pipeline_type=pipeline,
        base_dir=base_dir,
    )
    return result


COMMANDS = {
    "discover": cmd_discover,
    "provider_menu": cmd_provider_menu,
    "support_envelope": cmd_support_envelope,
    "list_available": cmd_list_available,
    "run_tool": cmd_run_tool,
    "init_project": cmd_init_project,
}


# ── 入口 ──────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "用法: worker.py <命令> [参数...]"}))
        sys.exit(1)

    cmd = sys.argv[1]
    handler = COMMANDS.get(cmd)
    if not handler:
        print(json.dumps({"error": f"未知命令: {cmd}"}))
        sys.exit(1)

    if cmd == "run_tool":
        tool_name = sys.argv[2] if len(sys.argv) > 2 else ""
        params = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        result = handler(tool_name, params)
    elif cmd == "init_project":
        pipeline = sys.argv[2] if len(sys.argv) > 2 else ""
        project_id = sys.argv[3] if len(sys.argv) > 3 else ""
        title = sys.argv[4] if len(sys.argv) > 4 else ""
        result = handler(pipeline, project_id, title)
    else:
        result = handler()

    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
