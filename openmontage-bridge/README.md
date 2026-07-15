# OpenMontage Bridge

**OpenMontage 的隔离调用层。** 不修改、不污染 OpenMontage 项目，只通过 Python API 调用其能力。

## 设计原则

```
你的 Agent / 代码
      │
      ▼
openmontage-bridge/     ← 你的项目，完全独立
  ├── discovery          ← 工具发现
  ├── tool call          ← 单工具调用
  └── pipeline run       ← 完整流水线
      │
      ▼
OpenMontage/            ← 原地不动，零侵入
```

| 维度 | 方案 |
|------|------|
| **代码隔离** | Bridge 只 `subprocess` + `sys.path` 注入，不写 OpenMontage 文件 |
| **环境隔离** | 使用 OpenMontage 的 `.venv` 但不修改其依赖 |
| **版本锁定** | 通过 git tag/sha 感知 OpenMontage 版本 |
| **输出隔离** | 产物写到 `output/`，不污染 OpenMontage `projects/` |

## 快速开始

```python
from openmontage_bridge import Bridge

bridge = Bridge()

# 1. 发现能力
report = bridge.discover()
print(f"共 {len(report.all_tool_names)} 个工具")
for c in report.capabilities:
    print(f"  {c['capability']}: {c['configured']}/{c['total']}")

# 2. 调用工具
result = bridge.run_tool("tts_selector", {
    "text": "Hello, world!",
    "voice": "en-us",
})
print(result.success, result.data)

# 3. 查看流水线
for p in bridge.list_pipelines():
    print(f"{p.name} — {p.description[:60]}...")
```

## API 速览

| 方法 | 说明 |
|------|------|
| `discover()` | 执行 capability discovery |
| `provider_menu_summary()` | N of M 能力菜单 |
| `provider_menu()` | 完整提供商菜单 (含 install_instructions) |
| `support_envelope()` | 每个工具的完整 contract |
| `list_tools()` | 所有注册工具名称 |
| `list_available_tools()` | 当前可用工具 |
| `tool_info(name)` | 单个工具详情 |
| `run_tool(name, params)` | 调用单个工具 |
| `list_pipelines()` | 列出所有流水线 |
| `get_pipeline(name)` | 获取单条流水线信息 |
| `init_pipeline_project(...)` | 初始化流水线项目目录 |
| `make_video(prompt, pipeline)` | 一站视频制作入口 |

## 环境要求

- Python 3.10+
- OpenMontage 项目在 `../OpenMontage/` (可配置，SceneCraft 总目录下的兄弟项目)
- OpenMontage 的 `.venv` 已设置
