# 🎬 Video Factory

AI 视频制作全套件。三层架构，隔离调用。

```
User Concept
    ↓
ai-short-drama/           ← 9 Agent 创意制片工厂
    ↓ (调 bridge)
openmontage-bridge/       ← 隔离调用层 (零侵入)
    ↓ (subprocess)
OpenMontage/              ← AI 视频生成引擎 (上游不动)
```

## 目录

| 项目 | 路径 | 说明 |
|------|------|------|
| OpenMontage | `OpenMontage/` | 上游视频生成引擎 (只读，不动) |
| openmontage-bridge | `openmontage-bridge/` | 隔离调用层，主开发空间 |
| ai-short-drama | `ai-short-drama/` | 多 Agent 短剧创意输出 |

## 快速开始

```bash
# 1. 确保 OpenMontage 的 .venv 可用
cd OpenMontage && test -d .venv || python3 -m venv .venv

# 2. 运行 ai-short-drama (Demo 模式)
cd ../ai-short-drama && python run.py "你的创意概念"

# 3. 或通过 bridge 单步调 OpenMontage 工具
cd ../openmontage-bridge && python -c "
from openmontage_bridge import Bridge
b = Bridge()
print(b.discover().summary)
"
```
