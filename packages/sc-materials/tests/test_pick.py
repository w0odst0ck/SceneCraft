"""sc_materials 素材卡库单测（§7.1 的 pick 用例 + E4/E14/E16 等补充用例）。

M0 抽包：由主仓 tests/test_materials.py 迁入素材卡相关用例（用例逻辑未改）；
仅改 import 与 CLI 脚本定位（包内 pick.py，不依赖宿主路径）。
- 素材相关单测一律用 tmp_path 构造临时卡片，不读写仓库真实 cards/（数据安全红线）；
"""
import subprocess
import sys
from pathlib import Path

import pytest

import sc_materials.pick as pick_materials

# CLI 用例直接运行包内脚本（不依赖 pip install -e，包内 `pytest` 可独立通过）
PICK_SCRIPT = Path(pick_materials.__file__).resolve()
ROOT = PICK_SCRIPT.parent


# ── 辅助 ────────────────────────────────────────────────

def make_card(dir_: Path, stem: str, *, type_: str, tags, status: str = "原创",
              priority: str = "core", source: str = "", title: str = "测试卡标题",
              core: str = "核心设定：一段测试内容。", reusable: str = "可复用点：可用于某场戏。",
              copyright_note: str = "") -> Path:
    """在 dir_ 下写一张临时素材卡（文件名 = <stem>.md，id = stem），返回路径。"""
    tags_repr_val = tags_repr(tags)
    body = [
        "---",
        f"id: {stem}",
        f"type: {type_}",
        f"tags: {tags_repr_val}",
        f"status: {status}",
        f'source: "{source}"',
        f"priority: {priority}",
        "---",
        f"# {title}",
        "## 核心设定",
        core,
        "## 可复用点",
        reusable,
        "## 版权备注",
        copyright_note,
    ]
    p = dir_ / f"{stem}.md"
    p.write_text("\n".join(body) + "\n", encoding="utf-8")
    return p


def make_card_no_title(dir_: Path, stem: str, *, type_: str, tags, status: str = "原创",
                       priority: str = "core") -> Path:
    """写一张缺 `# 标题` 行的卡（E14 用），标题回退文件名 stem。"""
    body = [
        "---",
        f"id: {stem}",
        f"type: {type_}",
        f"tags: {tags_repr(tags)}",
        f"status: {status}",
        'source: ""',
        f"priority: {priority}",
        "---",
        "## 核心设定",
        "核心设定内容",
        "## 可复用点",
        "可复用点内容",
    ]
    p = dir_ / f"{stem}.md"
    p.write_text("\n".join(body) + "\n", encoding="utf-8")
    return p


def tags_repr(tags) -> str:
    if isinstance(tags, (list, tuple, set)):
        return "[" + ", ".join(str(t) for t in tags) + "]"
    return str(tags)


def cli(args: list[str]) -> subprocess.CompletedProcess:
    """以子进程运行 pick_materials.py（--cards-dir 由调用方传入 tmp_path）；60s 超时防 hang。"""
    try:
        return subprocess.run(
            [sys.executable, str(PICK_SCRIPT), *args],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"pick_materials CLI 子进程超时（>60s）：{exc}")


def run_studio(studio: str, project: str, artifacts_dir: Path, *extra: str,
               demo: bool = False) -> subprocess.CompletedProcess:
    """以子进程运行 studios/<studio>/run.py（demo 模式，不触发网络）；60s 超时防 hang。"""
    cmd = [sys.executable, str(ROOT / "studios" / studio / "run.py"),
           "--project", project, "--artifacts-dir", str(artifacts_dir), *extra]
    if demo:
        cmd.append("--demo")
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
                              timeout=60)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"{studio}/run.py 子进程超时（>60s）：{exc}")


def _import_run():
    import studios.studio_story.run as run_module
    return run_module


# ── §7.1 pick_materials 单测（14 个）──────────────────

def test_pick_filter_and_overlap(tmp_path):
    """命中按重叠度降序；零交集卡不出现。"""
    make_card(tmp_path, "a", type_="setting", tags=["赛博朋克", "悬疑"], status="原创",
              priority="core", title="A重叠2")
    make_card(tmp_path, "b", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="B重叠1")
    make_card(tmp_path, "c", type_="setting", tags=["爱情"], status="原创",
              priority="core", title="C零交集")
    out = pick_materials.pick_materials("赛博朋克,悬疑", cards_dir=tmp_path)
    assert out.index("### setting: A重叠2") < out.index("### setting: B重叠1")
    assert "C零交集" not in out


def test_pick_no_tags(tmp_path):
    """E1：无 tags → 空串；CLI --tags "" → exit 0、stdout 空。"""
    assert pick_materials.pick_materials("", cards_dir=tmp_path) == ""
    assert pick_materials.pick_materials(None, cards_dir=tmp_path) == ""
    r = cli(["--tags", "", "--cards-dir", str(tmp_path)])
    assert r.returncode == 0
    assert r.stdout == ""


def test_pick_empty_dir(tmp_path):
    """E2：空/不存在 cards 目录 → 空串，exit 0，不抛异常。"""
    assert pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path) == ""
    assert pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path / "不存在") == ""


def test_pick_truncation_under_2000(tmp_path):
    """E7：12 张长卡 → 输出 ≤2000；core 卡全部在场；每张 `### ` 块完整（不半切字段）。"""
    types = ["setting", "character", "beat", "theme", "line", "detail"]
    for i, t in enumerate(types):
        make_card(tmp_path, f"core-{i}", type_=t, tags=["赛博朋克"], status="原创",
                  priority="core", title=f"Core{i}", core="核" * 130, reusable="用" * 130)
    for i, t in enumerate(types):
        make_card(tmp_path, f"backup-{i}", type_=t, tags=["赛博朋克"], status="原创",
                  priority="backup", title=f"Backup{i}", core="核" * 130, reusable="用" * 130)
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert len(out) <= 2000
    for i in range(6):  # core 层天然排前，预算截断优先牺牲 backup 尾部
        assert f"Core{i}" in out
    # 每个出现的卡块都是完整卡：`### ` 块数与完整「可复用点」行数一致（无半切）
    assert out.count("### ") == out.count("**可复用点**：")


def test_pick_priority_order(tmp_path):
    """core 层优先：backup 卡重叠度更高时，core 卡仍排在 backup 前。"""
    make_card(tmp_path, "a", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="Core卡")
    make_card(tmp_path, "b", type_="setting", tags=["赛博朋克", "悬疑"], status="原创",
              priority="backup", title="Backup高重叠")
    out = pick_materials.pick_materials("赛博朋克,悬疑", cards_dir=tmp_path)
    assert out.index("### setting: Core卡") < out.index("### setting: Backup高重叠")


def test_pick_per_type_cap_2(tmp_path):
    """E17：3 张同 type 命中 → 该 type 恰输出 2 张。"""
    for i in range(3):
        make_card(tmp_path, f"c{i}", type_="character", tags=["赛博朋克"], status="原创",
                  priority="core", title=f"角色{i}")
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert out.count("### character: ") == 2


def test_pick_status_annotation(tmp_path):
    """每卡块含 `- status: <三态>`；非原创卡强制含「结构参考勿照搬原文」+ 来源。"""
    make_card(tmp_path, "a", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="原创卡")
    make_card(tmp_path, "b", type_="character", tags=["赛博朋克"], status="灵感",
              priority="core", source="某作品", title="灵感卡", copyright_note="借鉴了结构X")
    make_card(tmp_path, "c", type_="theme", tags=["赛博朋克"], status="改写",
              priority="core", source="某作品", title="改写卡")
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert "- status: 原创" in out
    assert "- status: 灵感" in out
    assert "- status: 改写" in out
    assert out.count("⚠ 结构参考勿照搬原文") == 2
    assert "来源：某作品" in out


def test_pick_no_match(tmp_path):
    """E9：无任何卡命中 tags → 空串。"""
    make_card(tmp_path, "a", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="A")
    assert pick_materials.pick_materials("不存在的标签", cards_dir=tmp_path) == ""


def test_pick_malformed_skipped(tmp_path, capsys):
    """E3：坏 frontmatter 卡被跳过 + stderr 警告，其余卡正常返回。"""
    (tmp_path / "bad.md").write_text("没有 frontmatter 分隔符的内容\n", encoding="utf-8")
    make_card(tmp_path, "good", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="好卡")
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert "好卡" in out
    assert "跳过卡片 bad.md" in capsys.readouterr().err


def test_pick_invalid_status_skipped(tmp_path, capsys):
    """E15：status 非法卡被跳过（版权红线 fail-closed，绝不误标「原创」）。"""
    make_card(tmp_path, "bad", type_="setting", tags=["赛博朋克"], status="未知",
              priority="core", title="非法状态卡")
    make_card(tmp_path, "good", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="好卡")
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert "非法状态卡" not in out
    assert "好卡" in out
    assert "非法 status" in capsys.readouterr().err


def test_pick_missing_reusable_skipped(tmp_path, capsys):
    """E6：缺必填节「可复用点」→ 整卡跳过 + 警告（不注入不完整卡）。"""
    make_card(tmp_path, "bad", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="缺节卡", reusable="")
    make_card(tmp_path, "good", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="好卡")
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert "缺节卡" not in out
    assert "好卡" in out
    assert "可复用点" in capsys.readouterr().err


def test_pick_bad_type_skipped(tmp_path, capsys):
    """E4：type 不在六类枚举 → 跳过 + 警告，其余卡正常。"""
    make_card(tmp_path, "bad", type_="notatype", tags=["赛博朋克"], status="原创",
              priority="core", title="非法类型卡")
    make_card(tmp_path, "good", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="好卡")
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert "非法类型卡" not in out
    assert "好卡" in out
    assert "非法 type" in capsys.readouterr().err


def test_pick_missing_title_fallback(tmp_path, capsys):
    """E14：缺 # 标题 → title 回退文件名 stem + 警告，卡仍正常注入。"""
    make_card_no_title(tmp_path, "fallback卡", type_="setting", tags=["赛博朋克"],
                       status="原创", priority="core")
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert "### setting: fallback卡" in out  # 回退为文件名 stem
    assert "回退为文件名" in capsys.readouterr().err


def test_pick_invalid_priority_backup(tmp_path, capsys):
    """E16：priority 非法 → 保守降级为 backup + 警告，不因优先级误排。"""
    make_card(tmp_path, "a", type_="setting", tags=["赛博朋克"], status="原创",
              priority="must", title="非法优先级卡")
    make_card(tmp_path, "b", type_="setting", tags=["赛博朋克", "悬疑"], status="原创",
              priority="backup", title="Backup卡")
    out = pick_materials.pick_materials("赛博朋克,悬疑", cards_dir=tmp_path)
    # a 已降级 backup；层内按重叠度排序，b（重叠2）在 a（重叠1）前
    assert out.index("### setting: Backup卡") < out.index("### setting: 非法优先级卡")
    assert "降级为 backup" in capsys.readouterr().err


def test_pick_fullwidth_comma(tmp_path):
    """E12：--tags 全角逗号与半角逗号等效。"""
    make_card(tmp_path, "a", type_="setting", tags=["赛博朋克", "悬疑"], status="原创",
              priority="core", title="全角卡")
    r1 = cli(["--tags", "赛博朋克，悬疑", "--cards-dir", str(tmp_path)])
    r2 = cli(["--tags", "赛博朋克,悬疑", "--cards-dir", str(tmp_path)])
    assert r1.returncode == 0 and r2.returncode == 0
    assert r1.stdout == r2.stdout
    assert r1.stdout != ""  # 两张写法都命中同一张卡


def test_pick_non_utf8_skipped(tmp_path, capsys):
    """E13：非 UTF-8（GBK）卡片文件被跳过、不崩，其余卡正常。"""
    (tmp_path / "gbk.md").write_bytes("---\nid: gbk\ntype: setting\n".encode("gbk"))
    make_card(tmp_path, "good", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="好卡")
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert "好卡" in out
    assert "跳过卡片 gbk.md" in capsys.readouterr().err


def test_pick_single_card_overflow(tmp_path, capsys):
    """E8：单张卡本身超限（极端）→ 硬截该卡 + `…` + 警告，总长 ≤2000。"""
    make_card(tmp_path, "huge", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="超长卡", core="核" * 1500, reusable="用" * 1500)
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert len(out) <= 2000
    assert out.endswith("…")
    assert "硬截断" in capsys.readouterr().err


def test_pick_limit_one_overflow(tmp_path):
    """E8 边界：limit=1 → 只输出省略号（1 字符），不超限。"""
    make_card(tmp_path, "huge", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="超长卡", core="核" * 1500, reusable="用" * 1500)
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path, limit=1)
    assert len(out) <= 1


def test_pick_missing_core_skipped(tmp_path, capsys):
    """L2：缺必填节「核心设定」→ 整卡跳过 + 警告（与 E6 对称 fail-closed，不渲染空值）。"""
    make_card(tmp_path, "bad", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="缺核心卡", core="")
    make_card(tmp_path, "good", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="好卡")
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert "缺核心卡" not in out
    assert "好卡" in out
    assert "核心设定" in capsys.readouterr().err


def test_pick_unreadable_card_skipped(tmp_path, capsys, monkeypatch):
    """M2：读取卡抛 OSError（如权限不足）→ 整卡跳过 + 警告，其余卡正常，不崩。"""
    make_card(tmp_path, "good", type_="setting", tags=["赛博朋克"], status="原创",
              priority="core", title="好卡")
    (tmp_path / "bad.md").write_text(
        "---\nid: bad\ntype: setting\ntags: [赛博朋克]\nstatus: 原创\n---\n# 坏卡\n"
        "## 核心设定\nx\n## 可复用点\ny\n", encoding="utf-8")
    orig_read_text = Path.read_text

    def unreadable(self, *args, **kwargs):
        if self.name == "bad.md":
            raise PermissionError(f"权限不足，拒绝读取 {self.name}")
        return orig_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    out = pick_materials.pick_materials("赛博朋克", cards_dir=tmp_path)
    assert "坏卡" not in out
    assert "好卡" in out
    assert "跳过卡片 bad.md" in capsys.readouterr().err


