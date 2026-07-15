# AI短剧多Agent制作工厂 — OpenClaw Skill

当用户要求制作短剧/生成视频/运行多Agent制片流程时，使用本 Skill。

## 系统结构

```
用户概念 → orchestration/pipeline.py (编排器)
              │
              ▼ 按阶段调度
           agents/*.md (9 个 Agent SOUL)
              │
              ▼ 产出 JSON 交付物
           output/{project_id}/
              │
              ▼ (可选) 提交给 OpenMontage
           integration/video_producer.py
              │
              ▼
           openmontage-bridge/bridge.py (隔离调用)
```

## 执行流程

### 前置条件
```python
# 确保 bridge 已 discover
from openmontage_bridge import Bridge
bridge = Bridge()
bridge.discover()
```

### 一键执行
```bash
python projects/ai-short-drama/run.py "<你的概念>"
```

或者在代码中：
```python
from projects.ai_short_drama.run import run_short_drama
deliverables = run_short_drama(
    concept="赛博朋克短剧：快递员发现自己的义体在收集记忆",
    produce_video=False,  # True 会尝试调 OpenMontage 渲染
)
# deliverables = {prompts_for_ai_video, editing_blueprint, ...}
```

### Agent 通信方式
Agent 间通过**结构化 JSON 文件 + 文件路径引用**通信，不通过实时 IPC。

1. Producer 写 `mission_plan.json`
2. Writer 读 → 写 `script.json`
3. Director 读 → 写 `shot_list.json`
4. ArtDir/Actor/Cine 并行读 → 写各自产物
5. Critic 读所有 → 写 `critic_report.json`
6. Editor + Prompter 并行读 → 写 `editing_blueprint.json` + `prompt_list.json`
7. Critic 终审 → 打包交付物

## 交付物

输出在 `video-factory/ai-short-drama/output/{project_id}/`

| 文件 | 用途 |
|------|------|
| `prompts_for_ai_video.json` | 每条是完整的六要素视频生成提示词 |
| `editing_blueprint.json` | 剪辑时间线 (帧级精度) |
| `project_metadata.txt` | 总时长/帧率/画幅/情绪节点 |
| `production_report.json` | Critic 质检报告 |

## 模型配置

短剧系统默认使用 DeepSeek-V4-Flash。如需要更高精度，在 `orchestration/pipeline.py` 的 `AGENT_MODELS` 字典中修改。

## 隔离原则

- **不改 OpenMontage**: 通过 bridge 以 subprocess 调用
- **不改 bridge**: bridge 是独立的 Python 包
- **AI短剧系统产物完全独立**: output/ 目录归自己管
