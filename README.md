# 🎬 SceneCraft

AI 短剧全栈管线 — 从概念到可渲染交付物。

```
概念 → ai-short-drama (9 Agent 创意工厂) → openmontage-bridge → OpenMontage → 最终视频
```

## 组件

| 组件 | 路径 | 说明 | 许可证 |
|------|------|------|--------|
| **SceneCraft** | 本仓库 | 编排 + 桥接 + 短剧创意 | MIT |
| openmontage-bridge | `openmontage-bridge/` | 隔离调用层 (subprocess，不 import AGPL) | MIT |
| ai-short-drama | `ai-short-drama/` | 9 Agent 短剧制片工厂 | MIT |
| OpenMontage | `OpenMontage/` | AI 视频生成引擎 (上游 fork) | AGPL v3 |

## 快速开始

```bash
# 1. 确保 OpenMontage 的 .venv 可用
cd OpenMontage && test -d .venv || python3 -m venv .venv

# 2. 配置密钥
cd ../ai-short-drama && cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY

# 3. 运行短剧 (默认 Demo 模式，配 Key 后自动激活真实调用)
python run.py "你的创意概念"

# 4. 或通过 bridge 单步调 OpenMontage 工具
cd ../openmontage-bridge && python -c "
from openmontage_bridge import Bridge
b = Bridge()
r = b.discover()
print(f'{len(r.all_tool_names)} tools, {len(r.capabilities)} capabilities')
"
```

## 许可证

- **SceneCraft** (本仓库): [MIT](LICENSE)
- **OpenMontage**: [AGPL v3](https://github.com/calesthio/OpenMontage/blob/main/LICENSE)

AI 产出物归创作者所有，许可证不约束 AI 生成内容。
