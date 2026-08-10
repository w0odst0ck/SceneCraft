# Studio Render — agents 说明

渲染站**没有独立 Agent SOUL**（视频渲染由外部系统完成）。

Phase B 接入约定：
- 通过 `openmontage-bridge/bridge.py` 以隔离方式调用 OpenMontage（不改 bridge、不改 OpenMontage）。
- 渲染任务由 `04_prompt/prompt_list.json`（逐镜提示词）+ `05_edit/editing_blueprint.json`（帧级时间线）组装。
- 渲染完成后，把真实视频元信息（路径/时长/帧率）写回 `06_render/` 并更新 manifest 血缘。

本目录 Phase A 为空，Phase B 可在此放置渲染任务卡 / 队列文档。
