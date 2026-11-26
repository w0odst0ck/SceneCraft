# 🧠 openmontage-bridge 记忆存档

项目相关记录、决策、调试笔记。

## 2026-07-15

### 项目归档
- 从 `projects/` 搬至 `projects/SceneCraft/`
- `bridge.py` 默认 OM 路径改为 `_PARENT / "OpenMontage"`（原为 `_WORKSPACE / "projects" / "OpenMontage"`）
- Git 初始化，branch: main
- `.gitignore` 排除了 output/ __pycache__ .venv .env

### 已知问题
- `run_tool` 需要对应 API Key（OpenMontage 自行 load .env，bridge 不做密钥管理）
- `make_video` 的 pipeline 能 init 但 stages 因缺 Key 跑不完
