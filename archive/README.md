# archive/ — 已归档资产（不参与运行）

本目录存放**不再被运行时引用**的历史资产。保留是为了可追溯/可回滚，不影响 SceneCraft 运行。

## 为什么在这里

| 目录 | 归档原因 | 可否删除 |
|---|---|---|
| ~~`OpenMontage/`（220MB）~~ | **已于 2026-11-26 删除**（0 文件入仓、零运行时引用；上游可从 GitHub 重克隆） | 已删 |
| `ai-short-drama/` | v1 单管线实现。逻辑已移植进 `studios/` + `packages/`，仅剩 `.env` 读取依赖（已迁到根 `.env`） | ✅ 可删 |
| `openmontage-bridge/` | v1 隔离调用层。**零运行时引用**（render 站不再用它） | ✅ 可删 |
| `test-results-old/` | 2026-08~09 的调试产物（demo/smoke/早期 test-coffee 轮次） | ✅ 可删（`test-results/` 已保留关键证据） |
| `docs-2026-11-26/` | **plan/ + memory/ 原始记录**（6 份方案、9 篇日志、3 份 ocr 留档）——已蒸馏为 [`docs/SceneCraft-复盘-2026-11-26.md`](../docs/SceneCraft-复盘-2026-11-26.md) | ✅ 可删（复盘已完整覆盖） |

## 验证方式

归档后已实测：
```bash
.venv/bin/python -m pytest tests/ -q          # 140 passed
.venv/bin/python studios/run_pipeline.py --project x --concept y --demo   # 全链通
```

## 恢复方式

```bash
# 从归档恢复某个目录
mv archive/ai-short-drama ./
# 若已 git mv 过，从历史恢复：
git checkout <commit> -- ai-short-drama
```

## 已彻底移除

- `learning` symlink → 曾指向 `/mnt/d/ZZZ/NOTES/learning/scenecraft`（目标已移至 D 盘 `Archive/`，本地不再引用；用户确认不要）
- `OpenMontage/`（220MB）→ 2026-11-26 删除（零入仓零引用；上游可从 GitHub 重克隆）

## 蒸馏记录（2026-11-26）

`plan/` 与 `memory/` 已归档到 `docs-2026-11-26/`，内容蒸馏为一份复盘：

> **`docs/SceneCraft-复盘-2026-11-26.md`**（282 行）
> 含：四阶段时间线 · 资产盘点（真资产 vs 死资产）· 5 条教训 · 4 次认知转折 · 「如果重来一次」· 下一步建议