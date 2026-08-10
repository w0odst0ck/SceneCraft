# Studio Render — 渲染站（bridge 占位）

## 职责
消费提示词列表与剪辑蓝图，调用 openmontage-bridge 渲染视频产物。
**Phase A 仅占位**：输出 `video_placeholder.json`，真实渲染 Phase B 接入
`openmontage-bridge/bridge.py` 后替换。

## 归入 Agent
- （Phase B 接 bridge，无独立 Agent SOUL；`agents/README.md` 记录接入约定）

## 输入产物
| 短名 | 契约 | 来源 |
|------|------|------|
| `prompt` | `schemas/prompt_list.py::PromptList` | Studio Prompt（04_prompt） |
| `edit` | `schemas/editing_blueprint.py::EditingBlueprint` | Studio Edit（05_edit） |

## 输出产物
| 文件 | 契约 | 落盘 |
|------|------|------|
| `video_placeholder.json`（占位） | `run.py::RenderPlaceholder` | `<artifacts>/<project_id>/06_render/` |
| 视频产物（Phase B） | — | 同上目录 |

## 契约引用
- `schemas/artifact.py` — `ArtifactBase`
- 渲染任务组装：`schemas/prompt_list.py` + `schemas/editing_blueprint.py`

## 目录映射
manifest `studios` key：**`render`** ↔ 磁盘目录 **`06_render`**

## 运行
```bash
python studios/studio_render/run.py --project demo1
```
> 前置：`04_prompt/prompt_list.json` + `05_edit/editing_blueprint.json` 必须存在，否则友好报错。

## 断点续跑 / 人工修改
- 占位产物同样计入 manifest（血缘：`prompt` / `edit` 的 hash）。
- Phase B 渲染完成后将真实视频元信息写入 manifest / 产物，保持血缘可追溯。
