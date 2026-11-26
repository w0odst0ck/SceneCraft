# 📋 openmontage-bridge 规划

## 总体目标

OpenMontage 的隔离调用层，零侵入，只通过 Python API 调用其能力。

## 阶段

### Phase 1 ✅ 已完成
- [x] 核心 Bridge 类：discover / run_tool / list_pipelines / make_video
- [x] 路径解析：支持相对 + 绝对路径
- [x] subprocess 隔离执行
- [x] SkeLL.md + README + examples
- [x] git 初始化

### Phase 2 🚧 待推进
- [ ] 模式 B：FastAPI 微服务包装（REST API）
- [ ] 模式 C：事件驱动（消息队列 + 批量视频生产）
- [ ] 缓存机制：discover 结果缓存复用
- [ ] 错误重试 + 超时策略可配置
- [ ] `.env` 统一密钥管理（目前依赖 OpenMontage 自行加载）

### Phase 3 🌟 远期
- [ ] 多 worker 并发工具调用
- [ ] 视频产出 pipeline 的 checkpoint 恢复
- [ ] webhook 通知
