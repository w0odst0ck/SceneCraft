# 📋 ai-short-drama 规划

## 总体目标

输入一个概念 → 9 Agent 协同 → 产出可喂给视频 AI 的镜头提示词 + 剪辑时间线蓝图。

## 阶段

### Phase 1 ✅ 已完成
- [x] 9 Agent Soul Prompt（producer / writer / director / art_director / actor / cinematographer / editor / prompter / critic）
- [x] 编排器 pipeline.py（7 阶段：producer → writer → director → refine → critic → dual-track → critic-final）
- [x] Schema 定义（mission_plan / script / shot_list / dual_track / critic_report）
- [x] Demo 模式可跑通（2 次 Demo 运行已验证）
- [x] DeepSeek API 调用集成（model: deepseek-chat）
- [x] Bridge 集成 video_producer.py
- [x] git 初始化

### Phase 2 🚧 待推进
- [ ] Bug 修复：`len(scene for scene ...)` → `len(script.scenes)`
- [ ] 密钥管理：从硬编码改为 `.env` 读取
- [ ] `_stage_parallel_refine()` 的 Actor/Cine 改成真实 DeepSeek 调用
- [ ] 跑一条真实概念验证全流程（非 Demo 模式）
- [ ] Agent 输出 JSON 解析异常时 fallback 更优雅
- [ ] 增加 Agent 调用重试 + 超时策略

### Phase 3 🌟 远期
- [ ] 异步并行 Agent 调度（refine 阶段 3 Agent 同时调）
- [ ] Critic 反馈循环（质量不够可自动回退重来）
- [ ] 支持多轮对话式创作（用户介入修改）
- [ ] 自定义 Agent 角色（用户可增删）
