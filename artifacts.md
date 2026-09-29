# 内置字幕显示与烧录修复产物

| 产物 | 路径 | 说明 |
|---|---|---|
| 图片字幕烧录实现 | `core/ffmpeg_engine.py` | PGS/VobSub 采用时长修复、画布对齐、保持字幕帧和缩放后输出。 |
| 字幕名称格式化 | `core/subtitle.py` | 提供短下拉名称和完整可换行详情。 |
| 界面更新 | `gui/app.py` | 完整字幕信息独立显示在下拉框下方。 |
| 回归测试 | `tests/test_embedded_subtitles.py`、`tests/test_subtitle_labels.py` | 覆盖图片字幕命令、长名称和真实文字字幕烧录。 |
| 已发布 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.6 | 图片字幕和完整名称修复版。 |
| 当前计划发布 | GitHub Release `v1.0.7` | 开始/取消按钮始终可见的布局修复版。 |
