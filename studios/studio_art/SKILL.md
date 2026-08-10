# Studio Art — 美术站

## 职责
阅读剧本，定义整剧视觉语言（色彩基调 / 材质 / 光照 / 角色造型 / 美术备注），
产出视觉圣经 `visual_bible.json`。

## 归入 Agent
- `agents/art_director.md` — 美术指导：色彩基调与剧本情绪曲线对齐，所有镜头共享一致美术语言

## 输入产物
| 短名 | 契约 | 来源 |
|------|------|------|
| `script` | `schemas/script.py::Script` | Studio Story（01_script） |

## 输出产物
| 文件 | 契约 | 落盘 |
|------|------|------|
| `visual_bible.json` | `schemas/visual_bible.py::VisualBible` | `<artifacts>/<project_id>/02_art/visual_bible.json` |

## 契约引用
- `schemas/artifact.py` — `ArtifactBase`
- `schemas/visual_bible.py` — `VisualBible` / `ColorPalette` / `CharacterDesign`

## 目录映射
manifest `studios` key：**`art`** ↔ 磁盘目录 **`02_art`**

## 运行
```bash
python studios/studio_art/run.py --project demo1
```
> 前置：`01_script/script.json` 必须存在（先跑 Studio Story），否则友好报错提示先跑上游。

## 断点续跑 / 人工修改
- 重跑本工作室会按 manifest 血缘记录本次消费的 `script` hash。
- 人工修改 `visual_bible.json` 后：`edited_by="human"`、递增 `version`。
