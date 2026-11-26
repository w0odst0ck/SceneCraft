# AI短剧多智能体制片工厂

**输入一个概念，输出可逐条喂给视频 AI 的镜头提示词 + 精准剪辑时间线蓝图。**

```
概念 → 9 Agent 协同 → 交付物 (prompts + blueprint) → [OpenMontage Bridge] → 最终视频
```

## 架构

```
┌─ 用户概念 ─────────────────────────────────────────────┐
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─ 总制片人 (Producer) ─── 拆解任务、调度所有 Agent ──┐
└────────────────────────┬────────────────────────────────┘
                         │
    ┌──────────┬──────────┼──────────┬──────────┐
    ▼          ▼          ▼          ▼          ▼
 ┌──────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌──────────┐
 │编剧  │ │导演   │ │美术指导│ │演员  │ │摄影指导 │
 │Writer│ │Director│ │Art Dir │ │Actor │ │Cine     │
 └──────┘ └────────┘ └────────┘ └──────┘ └──────────┘
    │          │          │          │          │
    └──────────┴──────────┼──────────┴──────────┘
                         ▼
                  ┌──────────────┐
                  │ Critic 初审  │
                  └──────────────┘
                         ▼
           ════════════════════════════
           ◆ 双轨并行 (关键分水岭) ◆
           ════════════════════════════
                         │
          ┌──────────────┴──────────────┐
          ▼                              ▼
   ┌──────────────┐             ┌──────────────────┐
   │ 剪辑师       │             │ 提示词工程师     │
   │ Editor       │             │ Prompter         │
   │ → 时间线蓝图  │             │ → 单镜头提示词    │
   └──────────────┘             └──────────────────┘
          │                              │
          └──────────────┬──────────────┘
                         ▼
                  ┌──────────────┐
                  │ Critic 终审  │
                  └──────────────┘
                         ▼
          ┌──────────────────────────────┐
          │ 最终交付物                    │
          │ ① prompts_for_ai_video.json  │
          │ ② editing_blueprint.json     │
          │ ③ project_metadata.txt       │
          │ ④ production_report.json     │
          └──────────────────────────────┘
```

## 9 Agent 角色

| Agent | 角色 | 职责 | 模型 |
|-------|------|------|------|
| producer | 总制片人 | 任务拆解、调度、裁决 | DeepSeek-V4-Pro |
| writer | 编剧 | 剧本创作、情绪曲线 | DeepSeek-V4-Pro |
| director | 导演 | 分镜拆解、Shot List | DeepSeek-V4-Pro |
| art_director | 美术指导 | 视觉风格、色彩基调 | DeepSeek-V4-Pro |
| actor | 演员 | 角色表演细节 | DeepSeek-V4-Flash |
| cinematographer | 摄影指导 | 机位、焦段、运镜 | DeepSeek-V4-Pro |
| editor | 剪辑师 | 时间线蓝图、转场 | DeepSeek-V4-Pro |
| prompter | 提示词工程师 | 单镜头六要素提示词 | DeepSeek-V4-Pro |
| critic | 批评家 | 质检、一致性审查 | DeepSeek-V4-Pro |

## 快速开始

```bash
# 默认概念运行
python run.py

# 指定概念
python run.py "古风玄幻短剧：剑客在梦境中预见自己的死亡"

# 完成后尝试渲染视频 (需配置 API Key)
python run.py "赛博朋克短剧" --render
```

## 输出

`output/<project_id>/`
- `prompts_for_ai_video.json` — 核心交付物：N个独立镜头提示词
- `editing_blueprint.json` — 时间线蓝图：入点/出点/转场
- `project_metadata.txt` — 元数据
- `production_report.json` — 质检报告

## 与 OpenMontage Bridge 的关系

```
ai-short-drama/            ← 你的项目 (多Agent创意生产)
    │
    ▼ (调 bridge 产物)
openmontage-bridge/        ← 桥接层 (隔离调用)
    │
    ▼ (subprocess)
OpenMontage/               ← 视频生成引擎 (不动)
```
