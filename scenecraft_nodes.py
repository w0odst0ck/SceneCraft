"""SceneCraft Kit — ComfyUI 自定义节点集。

设计原则：
1. **零 SceneCraft 依赖**：节点不 import sc_materials 等包，直接解析卡片文件格式。
   → 用户只需 clone 仓库 + 准备 cards 目录即可用，无需 pip install。
2. **输入即所见**：卡片目录路径暴露为节点参数，不写死任何本机路径。
3. **fail-closed**：非法卡（缺 status / 缺可复用点 / 非 UTF-8）跳过并 warning，绝不默认当原创。

节点清单：
- SC Material Library  — 按 tags 筛选素材卡 → 输出注入文本（带版权提示）
- SC Card Inspector    — 查看卡片库里有哪些 tag / 卡片（调试用）
"""
from __future__ import annotations

import re
from pathlib import Path

from typing_extensions import override

from comfy_api.latest import ComfyExtension, io, ui


# ── 卡片解析（与 SceneCraft sc-materials 的格式兼容，但不依赖其代码）──

_VALID_TYPES = {"setting", "character", "beat", "theme", "line", "detail"}
_VALID_STATUS = {"原创", "灵感", "改写"}  # 版权三态；缺失/非法 → 跳过（fail-closed）
_PRIORITIES = {"core", "backup"}


def _parse_frontmatter(text: str) -> dict[str, str]:
    """解析极简 YAML frontmatter（仅 key: value，不支持嵌套/列表语法）。

    素材卡 frontmatter 只用简单标量，不引 PyYAML 以保持零依赖。
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta: dict[str, str] = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta


def _parse_tags(raw: str) -> set[str]:
    """解析 tags：支持 `[a, b]` / `a, b` / 全角逗号。"""
    raw = re.sub(r"^\[|\]$", "", raw or "").strip()
    return {t.strip().strip("'\"") for t in re.split(r"[,\uFF0C]", raw) if t.strip()}


def _load_cards(cards_dir: Path) -> tuple[list[dict], list[str]]:
    """加载并校验卡片；返回 (合法卡列表, 警告列表)。异常卡只跳过，不中断。"""
    cards: list[dict] = []
    warnings: list[str] = []

    if not cards_dir.is_dir():
        return [], [f"卡片目录不存在: {cards_dir}"]

    for path in sorted(cards_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            warnings.append(f"{path.name}: 读取失败（{e}），已跳过")
            continue

        meta = _parse_frontmatter(text)
        status = meta.get("status", "").strip()
        ctype = meta.get("type", "").strip()

        # fail-closed：非法 type/status 一律跳过，绝不默认当「原创」注入
        if status not in _VALID_STATUS:
            warnings.append(f"{path.name}: status 非法或缺失（{status!r}），已跳过")
            continue
        if ctype not in _VALID_TYPES:
            warnings.append(f"{path.name}: type 非法或缺失（{ctype!r}），已跳过")
            continue

        tags = _parse_tags(meta.get("tags", ""))
        if not tags:
            warnings.append(f"{path.name}: tags 为空，不参与筛选")
            continue

        # 正文三节：核心设定 / 可复用点（必填）/ 版权备注
        body = text[end + 4:] if (end := text.find("\n---", 3)) != -1 else text
        m = re.search(r"##\s*可复用点\s*\n(.+?)(?=\n##|\Z)", body, re.S)
        if not m or not m.group(1).strip():
            warnings.append(f"{path.name}: 缺「可复用点」节，已跳过")
            continue
        reusable = m.group(1).strip()

        m2 = re.search(r"##\s*核心设定\s*\n(.+?)(?=\n##|\Z)", body, re.S)
        core = (m2.group(1).strip() if m2 else "")[:300]

        m3 = re.search(r"^#\s*(.+)$", body, re.M)
        title = (m3.group(1).strip() if m3 else path.stem)

        cards.append({
            "id": meta.get("id", path.stem),
            "title": title,
            "type": ctype,
            "tags": tags,
            "status": status,
            "source": meta.get("source", ""),
            "priority": meta.get("priority", "backup"),
            "core": core,
            "reusable": reusable,
        })

    return cards, warnings


def _render_card(card: dict) -> str:
    """渲染单张卡为注入文本。非原创强制带来源与「勿照搬」提示（版权红线）。"""
    lines = [f"### {card['type']}: {card['title']}", f"- status: {card['status']}"]
    if card["core"]:
        lines.append(f"**核心设定**：{card['core']}")
    lines.append(f"**可复用点**：{card['reusable']}")
    if card["status"] != "原创":
        src = card["source"] or "未标注"
        lines.append(f"⚠ 结构参考勿照搬原文（来源：{src}）")
    return "\n".join(lines)


def _pick(tags_str: str, cards_dir: str, limit_chars: int, per_type_max: int) -> tuple[str, str]:
    """返回 (注入正文, 状态摘要)。"""
    query = _parse_tags(tags_str)
    if not query:
        return "", "未提供 tags（不注入）"

    cards, warnings = _load_cards(Path(cards_dir))
    if not cards:
        summary = f"卡片库为空或全部非法；警告 {len(warnings)} 条"
        if warnings:
            summary += "：" + "；".join(warnings[:3])
        return "", summary

    # 命中：tag 有交集；排序：命中数降序 → core 优先
    matched = [(len(c["tags"] & query), c) for c in cards if c["tags"] & query]
    matched.sort(key=lambda x: (-x[0], 0 if x[1]["priority"] == "core" else 1))

    selected: list[dict] = []
    per_type: dict[str, int] = {}
    used = 0
    for _, card in matched:
        t = card["type"]
        if per_type.get(t, 0) >= per_type_max:
            continue
        block = _render_card(card)
        if used + len(block) > limit_chars and selected:
            break  # 预算不足则丢整卡（不半切）
        selected.append(card)
        per_type[t] = per_type.get(t, 0) + 1
        used += len(block) + 2

    if not selected:
        return "", f"tags={sorted(query)} 未命中任何卡片（库内 {len(cards)} 张）"

    body = "\n\n".join(_render_card(c) for c in selected)
    summary = (f"命中 {len(matched)} 张，注入 {len(selected)} 张"
               f"（类型 {', '.join(f'{k}×{v}' for k, v in per_type.items())}）"
               f" · {used}/{limit_chars} 字符")
    if warnings:
        summary += f" · 跳过 {len(warnings)} 张非法卡"
    return body, summary


# ── 节点 1：素材库筛选 ──────────────────────────────────────

class SCMaterialLibrary(io.ComfyNode):
    """按 tags 从素材卡库筛选卡片，输出可直接拼进 prompt 的注入文本。"""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="SC_MaterialLibrary",
            display_name="SC Material Library（素材库）",
            category="SceneCraft",
            description=(
                "按 tags 筛选素材卡（角色/桥段/主题/金句等），输出注入文本。"
                "非原创卡自动附来源与「勿照搬」提示（版权三态 fail-closed）。"
            ),
            inputs=[
                io.String.Input(
                    "tags",
                    default="",
                    multiline=False,
                    tooltip="逗号分隔的标签，如「治愈,善意」（精确交集匹配）",
                ),
                io.String.Input(
                    "cards_dir",
                    default="./story-materials/cards",
                    multiline=False,
                    tooltip="素材卡目录（含 *.md 卡片文件）",
                ),
                io.Int.Input(
                    "limit_chars",
                    default=2000,
                    min=0,
                    max=20000,
                    step=100,
                    tooltip="注入文本字符预算；预算不足时丢整卡，不半切",
                ),
                io.Int.Input(
                    "per_type_max",
                    default=2,
                    min=1,
                    max=10,
                    step=1,
                    tooltip="每类（setting/character/beat/theme/line/detail）最多注入几张",
                ),
            ],
            outputs=[
                io.String.Output(display_name="material_text"),
                io.String.Output(display_name="summary"),
            ],
            is_output_node=True,  # 纯文本输出：让它能作为工作流的终点（否则 prompt_no_outputs）
        )

    @classmethod
    def execute(cls, tags: str, cards_dir: str, limit_chars: int,
                per_type_max: int) -> io.NodeOutput:
        body, summary = _pick(tags, cards_dir, limit_chars, per_type_max)
        print(f"[SC Material Library] {summary}")
        # 同时把正文带到前端预览（纯文本输出不会自动进 outputs/history）
        return io.NodeOutput(body, summary, ui=ui.PreviewText(body))


# ── 节点 2：卡片库检查器 ────────────────────────────────────

class SCCardInspector(io.ComfyNode):
    """列出素材卡库的统计信息（types / tags / 非法卡），用于调试和筛选。"""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="SC_CardInspector",
            display_name="SC Card Inspector（卡片检查）",
            category="SceneCraft",
            description="查看素材卡库统计：有效卡片数、类型分布、全部可用 tags、非法卡警告。",
            inputs=[
                io.String.Input(
                    "cards_dir",
                    default="./story-materials/cards",
                    multiline=False,
                    tooltip="素材卡目录",
                ),
            ],
            outputs=[
                io.String.Output(display_name="report"),
            ],
            is_output_node=True,  # 纯文本输出：允许单独作为终点运行（用于调试）
        )

    @classmethod
    def execute(cls, cards_dir: str) -> io.NodeOutput:
        cards, warnings = _load_cards(Path(cards_dir))
        if not cards:
            report = f"未加载到任何有效卡片（{cards_dir}）\n" + "\n".join(warnings[:10])
            print(f"[SC Card Inspector] {report}")
            return io.NodeOutput(report, ui=ui.PreviewText(report))

        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        all_tags: set[str] = set()
        for c in cards:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
            by_status[c["status"]] = by_status.get(c["status"], 0) + 1
            all_tags |= c["tags"]

        lines = [
            f"目录: {cards_dir}",
            f"有效卡片: {len(cards)}",
            f"类型分布: " + ", ".join(f"{k}×{v}" for k, v in sorted(by_type.items())),
            f"版权状态: " + ", ".join(f"{k}×{v}" for k, v in sorted(by_status.items())),
            f"可用 tags（{len(all_tags)}）: " + ", ".join(sorted(all_tags)),
        ]
        if warnings:
            lines.append(f"跳过 {len(warnings)} 张（前 5 条）:")
            lines.extend(f"  - {w}" for w in warnings[:5])

        report = "\n".join(lines)
        print(f"[SC Card Inspector]\n{report}")
        return io.NodeOutput(report, ui=ui.PreviewText(report))


# ── 注册 ────────────────────────────────────────────────────

class SceneCraftExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [SCMaterialLibrary, SCCardInspector]


async def comfy_entrypoint() -> SceneCraftExtension:
    return SceneCraftExtension()