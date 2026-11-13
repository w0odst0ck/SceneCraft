# sc-contracts

SceneCraft 产物契约（pydantic v2）：跨工作室产物共享血缘字段
（`upstream_hash` / `edited_by` / `version` / `output_hash`）。
M0 抽包：由主仓 `schemas/` 原样搬迁，字段语义与校验规则未改动。

- `ArtifactBase`、`content_hash()`
- `Script` / `Scene` / `DialogueLine`、`VisualBible`、`ShotList` / `Shot`、
  `PromptList` / `ShotPrompt`、`EditingBlueprint`、`RenderPlan`、`QcReport`
- `Manifest` / `StudioStatus`（项目台账，非产物）

```python
from sc_contracts import ShotList

shot_list = ShotList.model_validate(data)
print(shot_list.compute_hash())
```
