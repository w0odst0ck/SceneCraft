# OpenMontage Bridge — OpenClaw Skill

当用户通过 **bridge 层** 请求视频制作、工具调用、能力发现时，使用本 Skill。

## 隔离原则

**bridge 和 OpenMontage 是两个独立项目，互不污染。**

| 项目 | 路径 | 准入门 |
|------|------|--------|
| OpenMontage | `SceneCraft/OpenMontage/` | ❌ 只读，不写任何文件 |
| openmontage-bridge | `SceneCraft/openmontage-bridge/` | ✅ 开发和输出在此 |
| 输出产物 | `SceneCraft/openmontage-bridge/output/` | ✅ bridge 的工作区 |

## 初始化

```python
from openmontage_bridge import Bridge

bridge = Bridge(
    openmontage_path="../OpenMontage",           # 或绝对路径
    output_root="output",
)

# 首次使用必须先 discover
bridge.discover()
```

## 能力查询

```python
# N of M 摘要 (给用户看的)
summary = bridge.provider_menu_summary()
for c in summary["capabilities"]:
    print(f"{c['capability']}: {c['configured']}/{c['total']}")

# 工具列表
all_tools = bridge.list_tools()
available = bridge.list_available_tools()

# 单工具详情
info = bridge.tool_info("tts_selector")
```

## 工具调用

```python
result = bridge.run_tool(
    tool_name="tts_selector",
    params={
        "text": "要配音的文字",
        "voice": "zh-CN",
    },
    timeout=120,
)

if result.success:
    audio_path = result.data["output_path"]
    cost = result.cost_usd
else:
    print(f"调用失败: {result.error}")
```

## 流水线

```python
# 列出流水线
pipelines = bridge.list_pipelines()
for p in pipelines:
    print(f"{p.name} — {p.stability}")

# 获取流水线详情
info = bridge.get_pipeline("animated-explainer")
print(info.stages)  # ["research", "proposal", "script", ...]

# 初始化视频制作项目
status = bridge.make_video(
    prompt="制作一个关于黑洞的60秒解说视频",
    pipeline="animated-explainer",
)
print(f"项目目录: {status.artifacts['project_dir']}")
```

## 工作流模式

### 模式 A：Agent 直接编排 (当前)
Agent（我）通过 bridge Python API 直接调用 OpenMontage 能力。
适合：单次交互、快速原型、实验。

### 模式 B：微服务 (未来扩展)
Bridge 可加一层 FastAPI/Flask 暴露 REST API。
适合：独立部署、多语言客户端、持续运行的后台服务。

### 模式 C：事件驱动 (未来扩展)
Bridge + 消息队列处理异步任务。
适合：大量批量视频生产、队列管理。

## 注意事项

1. **Bridge 不缓存状态。** 每次 `run_tool` 都是独立的 subprocess 调用。
2. **.env 密钥由 OpenMontage 自行加载。** Bridge 不做密钥管理。
3. **输出目录隔离。** 所有产物写 `output/<project_id>/`，不碰 OpenMontage 的 `projects/`。
4. **流水线的"人工审批阶段"** 在 bridge 层会返回 `awaiting_human` 状态，需要外部调用者处理审批逻辑。
