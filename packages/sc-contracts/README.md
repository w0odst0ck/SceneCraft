# sc-contracts

SceneCraft 产物契约（pydantic v2）：跨工作室产物共享血缘字段
（`upstream_hash` / `edited_by` / `version` / `output_hash`）。

本包零第三方依赖（仅 pydantic），**不依赖 SceneCraft 主仓**，可独立安装使用。

## 安装

```bash
pip install -e packages/sc-contracts   # 仓库内可编辑安装
# 或发布后：pip install sc-contracts
```

## 最小用法

```python
from sc_contracts import Script, ShotList

script = Script.demo()                     # 字段齐全的示例剧本，可直接校验结构
print(script.title, len(script.scenes))

shot_list = ShotList.demo()                # 已是校验通过的示例；也可传 dict/JSON：
# ShotList.model_validate({"target_shots": 1, "shots": [{...}]})
print(len(shot_list.shots), shot_list.compute_hash())   # 血缘 hash → downstream.upstream_hash
```

## 内容

- `ArtifactBase`、`content_hash()`
- `Script` / `Scene` / `DialogueLine`、`VisualBible`、`ShotList` / `Shot`、
  `PromptList` / `ShotPrompt`、`EditingBlueprint`、`RenderPlan`、`QcReport`
- `Manifest` / `StudioStatus`（项目台账，非产物）

## 环境变量

无。
