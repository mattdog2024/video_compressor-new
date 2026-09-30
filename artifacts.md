# 内置字幕显示与烧录修复产物

| 产物 | 路径 | 说明 |
|---|---|---|
| 图片字幕烧录实现 | `core/ffmpeg_engine.py` | PGS/DVB/VobSub/XSub 自动使用 HandBrake 原生烧录；文本字幕继续使用 FFmpeg。 |
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
| 推荐下载 | https://github.com/mattdog2024/video_compressor-new/releases/download/v1.0.11/VideoCompressor-v1.0.11-windows-x64.exe | v1.0.11，ASS/SRT 大字号可读性修复版。 |
| v1.0.11 发布页 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.11 | 正式发布页。 |
| v1.0.11 构建记录 | https://github.com/mattdog2024/video_compressor-new/actions/runs/36653311723 | 34 项回归测试、Windows 打包和上传均成功。 |
| 推荐下载 | https://github.com/mattdog2024/video_compressor-new/releases/download/v1.0.12/VideoCompressor-v1.0.12-windows-x64.exe | v1.0.12，Windows 内置 ASS 标准化修复版。 |
| v1.0.12 发布页 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.12 | 正式发布页。 |
| v1.0.12 构建记录 | https://github.com/mattdog2024/video_compressor-new/actions/runs/36654576727 | 37 项回归测试、Windows 打包和上传均成功。 |
| 推荐下载 | https://github.com/mattdog2024/video_compressor-new/releases/download/v1.0.13/VideoCompressor-v1.0.13-windows-x64.exe | v1.0.13，480p 字幕适中和极速体积控制版。 |
| v1.0.13 发布页 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.13 | 正式发布页。 |
| v1.0.13 构建记录 | https://github.com/mattdog2024/video_compressor-new/actions/runs/36655787889 | 40 项回归测试、Windows 打包和上传均成功。 |
| 推荐下载 | https://github.com/mattdog2024/video_compressor-new/releases/download/v1.0.14/VideoCompressor-v1.0.14-windows-x64.exe | v1.0.14，单语与中英双语字幕自动尺寸优化版。 |
| v1.0.14 发布页 | https://github.com/mattdog2024/video_compressor-new/releases/tag/v1.0.14 | 正式发布页。 |
| v1.0.14 构建记录 | https://github.com/mattdog2024/video_compressor-new/actions/runs/36659038003 | 43 项回归测试、Windows 打包和上传均成功。 |
| 当前计划发布 | GitHub Release `v1.0.15` | PGS/DVB/VobSub 原生烧录与极速画质修复版。 |
| PGS 原生烧录实现 | `core/ffmpeg_engine.py`、`utils/helpers.py` | 图片字幕自动切到 HandBrakeCLI；SRT/ASS/SSA 继续走 FFmpeg。 |
| 图片字幕组件 | `assets/handbrake/HandBrakeCLI.exe`（Actions 自动下载） | 固定 HandBrakeCLI 1.11.2，并校验 SHA-256 与附带 GPLv2 许可证。 |
| 新增验证 | `tests/test_handbrake_bitmap_subtitles.py` | 真实 PGS 样本逐帧验证字幕像素确实烧入画面。 |
