# 内置字幕显示与烧录修复产物

| 产物 | 路径 | 说明 |
|---|---|---|
| 图片字幕烧录实现 | `core/ffmpeg_engine.py` | PGS/VobSub 采用时长修复、画布对齐、保持字幕帧和缩放后输出。 |
| 字幕名称格式化与选择 | `core/subtitle.py` | 提供短下拉名称、完整可换行详情及单文件字幕选择逻辑。 |
| 逐文件界面 | `gui/app.py` | 每个队列文件各自一行字幕选择和完整字幕信息，列表支持滚动。 |
| 回归测试 | `tests/test_embedded_subtitles.py`、`tests/test_subtitle_labels.py`、`tests/test_per_file_subtitle_selection.py` | 覆盖图片字幕、长名称、真实文字字幕烧录和三个文件独立选择。 |
| 已发布 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.6 | 图片字幕和完整名称修复版。 |
| 已发布 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.7 | 开始/取消按钮始终可见的布局修复版。 |
| 已发布 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.8 | ASS/文字字幕清理和真正黑色描边修复版。 |
| 当前计划发布 | GitHub Release `v1.0.9` | 每个视频可单独选择内置字幕轨的批量处理版。 |
