# 内置字幕显示与烧录修复关键结论

| 项目 | 结论 |
|---|---|
| 长名称显示 | 下拉框只显示“第几条 / 语言 / 类型”，完整名称改到下方可换行区域，避免片名或字幕标题被截断。 |
| 文字内置字幕 | SRT、ASS、SSA、MovText 等直接从原视频容器烧录，不走临时 SRT 提取。 |
| 图片内置字幕 | PGS、DVD/VobSub、DVB、XSub 走图片叠加；加入 `-fix_sub_duration`、`scale2ref` 和 `repeatlast=1`，避免时长丢失、尺寸不匹配或字幕一闪而过。 |
| 默认选择规则 | “自动选择”会优先烧录每个视频的默认字幕，没有默认则第一条；也可手动选指定字幕流。 |
| 平台兼容 | 烧录后仍输出 H.264 Main、8 位 yuv420p、AAC-LC 48kHz MP4。 |
| 外部依据 | 图片字幕按视频画布缩放的 `scale2ref` 用法参考：https://superuser.com/questions/1759347/using-overlay-on-pgs-subtitles-is-putting-them-in-the-wrong-position 。DVD 图片字幕用 FFmpeg `overlay` 烧录的基础命令参考：https://bbs.archlinux.org/viewtopic.php?id=180688 。 |
| 网络完整性 | 本次仅修改字幕处理与界面显示；没有网络、代理、防火墙或系统网络设置代码。 |
