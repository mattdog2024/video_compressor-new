# 内置字幕显示与烧录修复产物

| 产物 | 路径 | 说明 |
|---|---|---|
| 图片字幕烧录实现 | `core/ffmpeg_engine.py` | PGS/VobSub 采用时长修复、画布对齐、保持字幕帧、按输出高度自动放大和底部居中。 |
| 字幕名称格式化与选择 | `core/subtitle.py` | 提供短下拉名称、完整可换行详情及单文件字幕选择逻辑。 |
| 逐文件界面 | `gui/app.py` | 每个队列文件各自一行字幕选择和完整字幕信息，列表支持滚动。 |
| 回归测试 | `tests/test_embedded_subtitles.py`、`tests/test_text_subtitle_normalization.py`、`tests/test_subtitle_labels.py`、`tests/test_per_file_subtitle_selection.py`、`tests/test_bitmap_subtitle_autosize.py` | 覆盖图片字幕、文字字幕、长名称、三个文件独立选择及自动适应大小。 |
| 已发布 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.6 | 图片字幕和完整名称修复版。 |
| 已发布 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.7 | 开始/取消按钮始终可见的布局修复版。 |
| 已发布 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.8 | ASS/文字字幕清理和真正黑色描边修复版。 |
| 已发布 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.9 | 每个视频可单独选择内置字幕轨的批量处理版。 |
| 已发布 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.10 | v1.0.10，文字和图片字幕自动适应大小版。 |
| v1.0.10 发布页 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.10 | 正式发布页。 |
| v1.0.10 构建记录 | https://github.com/mattdog2024/video_compressor-new/actions/runs/36652094503 | 33 项回归测试、Windows 打包和上传均成功。 |
| 当前计划发布 | GitHub Release `v1.0.11` | ASS/SRT 的 480p、720p、1080p 大字号可读性修复版。 |
