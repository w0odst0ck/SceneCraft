#!/usr/bin/env python3
"""story-materials/scripts/pick_materials.py — 素材卡筛选与注入文本拼装（纯 stdlib）

数据流：解析 cards/*.md（正则 frontmatter，无 PyYAML）→ tag 交集筛选 →
两级排序（core 层优先 → 层内重叠度降序 → id 升序确定性）→ 每类 ≤2 →
拼 markdown 卡块 → ≤2000 字符预算截断（丢整卡、不半切字段；极端单卡超限才硬截）。

CLI：
    python story-materials/scripts/pick_materials.py --tags 赛博朋克,悬疑 \\
        [--cards-dir DIR] [--limit 2000]

作为库（run.py 用）：
    from pick_materials import pick_materials
    body = pick_materials("赛博朋克,悬疑")   # 返回卡块正文（不含 '## 参考素材' 标题）
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── 常量 ────────────────────────────────────────────────
SIX_TYPES = {"setting", "character", "beat", "theme", "line", "detail"}
STATUSES = {"原创", "灵感", "改写"}   # 版权三态（fail-closed，非法一律跳过）
PRIORITIES = {"core", "backup"}
DEFAULT_CARDS_DIR = Path(__file__).resolve().parents[1] / "cards"  # story-materials/cards
LIMIT = 2000                        # 注入字符预算（CLI 默认值）
PER_TYPE_CAP = 2                    # 每类（type）最多取 2 张
HEADER = "## 参考素材\n\n"          # CLI 输出头（pick_materials() 本身不带）


class MalformedCard(Exception):
    """单张卡片数据异常（frontmatter 缺失 / 非法字段 / 缺必填节）。"""


@dataclass
class Card:
    id: str
    type: str
    tags: set[str]
    status: str
    source: str
    priority: str            # core | backup
    title: str
    core: str
    reusable: str
    copyright_note: str


# ── 解析 ────────────────────────────────────────────────

def _warn(msg: str) -> None:
    print(f"[警告] {msg}", file=sys.stderr)


def parse_card(path: Path) -> Card:
    """解析单张素材卡；数据异常抛 MalformedCard（由 load_cards 捕获后跳过）。

    - 正则 frontmatter：`key: value`，忽略非该格式行
    - type 六类枚举校验（非法抛错）；status 三态 fail-closed（绝不误标「原创」）
    - tags 支持 `[a, b]` / `a, b` / 全角逗号，解析为空视为无匹配（不抛错）
    - priority 缺失→backup；非法→保守降级 backup + 警告
    - 正文：标题 = 第一个 `# ` 行（缺失回退文件名 stem + 警告）；
      三节 = 按 `## ` 切分；缺「核心设定」/「可复用点」必填节 → 抛错（不注入不完整卡）
    """
    text = path.read_text(encoding="utf-8")  # UnicodeDecodeError 由 load_cards 捕获
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise MalformedCard("缺少 frontmatter 起始 ---")
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        raise MalformedCard("缺少 frontmatter 结束 ---")

    fm: dict[str, str] = {}
    for ln in lines[1:close]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", ln.strip())
        if m:
            fm[m.group(1)] = m.group(2).strip()

    # type：六类枚举，非法 fail-closed（E4）
    typ = fm.get("type", "").strip()
    if typ not in SIX_TYPES:
        raise MalformedCard(f"非法 type: {typ!r}")

    # status：三态 fail-closed，非法/缺失直接跳过，绝不默认「原创」（E15）
    status = fm.get("status", "").strip()
    if status not in STATUSES:
        raise MalformedCard(f"非法 status: {status!r}")

    # priority：缺失→backup；非法→保守降级 backup + 警告（E16，不因优先级误排）
    priority = fm.get("priority", "").strip() or "backup"
    if priority not in PRIORITIES:
        _warn(f"卡片 {path.name} 的 priority 非法（{priority!r}），保守降级为 backup")
        priority = "backup"

    # id：frontmatter 声明优先，缺失回退文件名 stem
    card_id = fm.get("id", "").strip() or path.stem

    # tags：支持 "[a, b]" / "a, b" / 全角逗号（E12）；解析为空 → 空集 + 警告（E5）
    raw = re.sub(r"^\[|\]$", "", fm.get("tags", "").strip())
    tags = {t.strip().strip("'\"") for t in re.split(r"[,\uFF0C]", raw) if t.strip()}
    if not tags:
        _warn(f"卡片 {path.name} 的 tags 缺失或解析为空，视为无匹配（不参与筛选）")

    source = fm.get("source", "").strip().strip("'\"")
    if status != "原创" and not source:
        # 版权红线：非原创必标 source（3.1 契约），缺失 → 跳过，绝不带空来源注入
        raise MalformedCard("status≠原创 但缺少 source（非原创必标来源）")

    # 正文：标题 = 第一个 "# " 行；三节 = 按 "## " 切分（去空行）
    body = lines[close + 1:]
    title: str | None = None
    for ln in body:
        m = re.match(r"^#\s+(.+)$", ln)
        if m:
            title = m.group(1).strip()
            break
    if title is None:  # E14：缺标题回退文件名 stem + 警告
        title = path.stem
        _warn(f"卡片 {path.name} 缺少 # 标题，回退为文件名 {path.stem}")

    sections: dict[str, list[str]] = {}
    cur: str | None = None
    for ln in body:
        if ln.startswith("## "):
            cur = ln[3:].strip()
            sections.setdefault(cur, [])
        elif cur is not None and ln.strip():
            sections[cur].append(ln.strip())
    core = "\n".join(sections.get("核心设定", [])).strip()
    reusable = "\n".join(sections.get("可复用点", [])).strip()
    copyright_note = "\n".join(sections.get("版权备注", [])).strip()

    if not core:  # L2：核心设定为必填节（与 E6 对称 fail-closed，缺则不注入，避免渲染空值）
        raise MalformedCard("缺少必填节「核心设定」")
    if not reusable:  # E6：可复用点为必填节，缺则跳过（fail-closed，不注入不完整卡）
        raise MalformedCard("缺少必填节「可复用点」")

    return Card(card_id, typ, tags, status, source, priority, title,
                core, reusable, copyright_note)


# ── 加载 ────────────────────────────────────────────────

def load_cards(cards_dir: Path) -> list[Card]:
    """读取目录下全部 .md 卡；单卡异常跳过 + 警告，库级不崩（E2/E3/E4/E6/E13/E15）。"""
    out: list[Card] = []
    cards_dir = Path(cards_dir)  # CLI 可能传入 str
    if not cards_dir.is_dir():  # E2：目录不存在 → 空
        return out
    # glob("*.md") 天然忽略隐藏文件（如 .foo.md）
    for p in sorted(cards_dir.glob("*.md")):
        try:
            out.append(parse_card(p))
        except (MalformedCard, UnicodeDecodeError, OSError) as exc:
            # E13：非 UTF-8 / 权限不足等 IO 异常也跳过，库级不崩（M2）
            _warn(f"跳过卡片 {p.name}：{exc}")
    return out


# ── 筛选与排序 ──────────────────────────────────────────

def select_cards(cards: list[Card], query_tags) -> list[Card]:
    """tag 交集筛选 + 两级排序（core 层优先 → 层内重叠度降序 → id 升序）+ 每类 ≤2。

    零交集卡不出现；同分按 id 升序，保证输出确定性（E17）。
    """
    q = set(query_tags)
    matched = [(len(c.tags & q), c) for c in cards if c.tags & q]
    matched.sort(key=lambda t: (0 if t[1].priority == "core" else 1,
                                -t[0], t[1].id))
    per_type: dict[str, int] = {}
    out: list[Card] = []
    for _, c in matched:
        if per_type.get(c.type, 0) >= PER_TYPE_CAP:  # E17：每类 ≤2
            continue
        per_type[c.type] = per_type.get(c.type, 0) + 1
        out.append(c)
    return out


# ── 渲染 ────────────────────────────────────────────────

def render_card(c: Card) -> str:
    """单张卡渲染为 markdown 卡块；非原创卡强制透传来源 + 「结构参考勿照搬原文」。"""
    lines = [
        f"### {c.type}: {c.title}",
        f"- status: {c.status}",
        f"**核心设定**：{c.core}",
        f"**可复用点**：{c.reusable}",
    ]
    if c.status != "原创":
        lines.append(f"⚠ 结构参考勿照搬原文（来源：{c.source}）")
        if c.copyright_note:
            lines.append(f"版权备注：{c.copyright_note}")
    return "\n".join(lines)


def render(selected: list[Card], limit: int) -> str:
    """按 2000 字符预算拼卡块：丢整卡、不半切字段（E7）。

    已按 core 优先排序，预算不足时从 backup 尾部开始丢；
    若首卡单卡即超限（极端，E8）→ 硬截该卡 + `…` + stderr 警告。
    """
    if limit <= 0:
        return ""  # 预算非正：无输出（防超限）
    parts: list[str] = []
    total = 0
    for c in selected:
        block = render_card(c)
        if total + len(block) + (1 if total else 0) <= limit:
            parts.append(block)
            total += len(block) + (1 if total else 0)
        # 放不下 → 跳过该卡继续（更小的 backup 卡仍可填充）
    if not parts and selected:  # E8：首卡单独超限 → 硬截（含 …）+ 警告
        head = render_card(selected[0])
        # limit==1 → 只输出省略号（1 字符）；limit<1 由函数开头 return "" 挡住
        parts.append(head[:max(0, limit - 1)] + "…" if limit >= 1 else "")
        _warn("单张卡超限，已硬截断")
    return "\n".join(parts)


# ── 对外接口 ────────────────────────────────────────────

def pick_materials(tags_str: str, cards_dir: Optional[Path] = None,
                   limit: int = LIMIT) -> str:
    """按逗号分隔 tags 挑卡并拼注入正文（不含最外层 '## 参考素材' 标题）。

    无 tags / 无匹配 / 空库 → 返回空串（调用方据此决定是否注入）。
    """
    tags = [t.strip() for t in re.split(r"[,\uFF0C]", tags_str or "") if t.strip()]
    if not tags:  # E1：无 tags → 空串
        return ""
    cards = load_cards(cards_dir or DEFAULT_CARDS_DIR)
    return render(select_cards(cards, tags), limit)


# ── CLI ─────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="按 tag 筛选素材卡并拼注入文本")
    parser.add_argument("--tags", required=True, help="逗号分隔标签，如 赛博朋克,悬疑")
    parser.add_argument("--cards-dir", default=None, help="卡片目录（默认 story-materials/cards）")
    parser.add_argument("--limit", type=int, default=LIMIT, help=f"输出字符预算（默认 {LIMIT}）")
    args = parser.parse_args(argv)

    body = pick_materials(args.tags, cards_dir=args.cards_dir,
                          limit=max(0, args.limit - len(HEADER)))
    if body:  # 无匹配 → 不输出任何内容，exit 0
        sys.stdout.reconfigure(encoding="utf-8")  # 保证中文输出编码
        sys.stdout.write(HEADER + body)            # 总输出 ≤ args.limit
    return 0


if __name__ == "__main__":
    sys.exit(main())
