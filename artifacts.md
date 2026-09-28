# 字幕烧录与并行压缩产物

| 产物 | 路径 | 说明 |
|---|---|---|
| 字幕烧录实现 | `core/ffmpeg_engine.py`、`core/subtitle.py`、`core/probe.py` | 文本和图片内置字幕分别走兼容烧录路径。 |
| 并行调度器 | `core/task_pool.py` | 强制限制最多 3 个并行任务。 |
| 界面更新 | `gui/app.py` | “内置字幕（烧录）”和“同时压缩 1/2/3 个任务”控件。 |
| 字幕回归测试 | `tests/test_embedded_subtitles.py` | 包含真实内置 SRT MKV 烧录验证。 |
| 并行回归测试 | `tests/test_task_pool.py`、`tests/test_output_path_reservation.py` | 验证 3 路上限和同名输出防覆盖。 |
| 已发布但不建议下载 | GitHub Release `v1.0.4` | 已发现 GUI 属性调用错误，正在由 v1.0.5 修正。 |
| 计划发布 | GitHub Release `v1.0.5` | 推送后由 Actions 自动生成修正版 EXE。 |
