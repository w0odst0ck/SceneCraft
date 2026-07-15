# 🧠 ai-short-drama 记忆存档

项目相关记录、决策、Agent 调试笔记。

## 2026-07-15

### 项目归档
- 从 `projects/` 搬至 `projects/video-factory/`
- `video_producer.py` 绝对路径改为动态解析
- Git 初始化，branch: main
- `.gitignore` 排除了 output/ __pycache__ .venv .env

### 架构决策
- 9 Agent 间通过 JSON 文件通信，不做实时 IPC
- Redundancy：Producer 拆解 → Writer → Director → 并行 Refine → Critic → 双轨 → Critic
- 隔离层：不改 OpenMontage，通过 bridge subprocess 调用

### 已知问题
- `pipeline.py:162` `len(scene for scene ...)` → 应改为 `len(script.scenes)`
- DEEPSEEK_API_KEY 硬编码在 pipeline.py 中（需要改为 .env）
- Actor / Cinematographer 未真正走 DeepSeek 调用，只用 Demo 值填充
- Demo 模式 2 次运行已验证，产物结构完整

### 已有 Demo 产出
| Project ID | 概念 | 镜头数 |
|-----------|------|--------|
| ai-drama-2cb9ad90 | （默认赛博朋克） | 20 shots |
| ai-drama-34769c88 | （默认赛博朋克） | 20 shots |
