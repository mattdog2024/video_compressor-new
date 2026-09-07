# 🎬 万能视频压缩器 v1.0

一个功能强大的视频压缩工具，支持将各种视频格式转换为720p H.264 MP4，清晰又小巧。

## ✨ 功能特性

### 核心功能
- 🎯 **万能格式转换** - 支持 MKV/AVI/MOV/FLV/WMV/WebM/TS 等常见格式转720p H.264 MP4
- 📺 **高清小体积** - CRF智能编码，画质与体积完美平衡
- 📝 **字幕烧录** - 支持烧录内置字幕和外挂字幕（SRT/ASS/SSA）
- 🔊 **音量调节** - 0-100音量自由控制
- ⏩ **跳过片头片尾** - 设置跳过开头/结尾秒数
- 🚀 **GPU硬件加速** - 自动检测NVIDIA/Intel/AMD GPU，极速压缩
- 📦 **批量处理** - 多文件队列式批量压缩

### 额外功能
- 📊 **实时进度** - 显示进度百分比、速度、剩余时间
- 🎨 **暗色主题** - 现代化深色UI，护眼舒适
- 🎚️ **预设质量** - 极速/快速/标准/高质量/无损 五档可选
- 📂 **输出自定义** - 自由选择输出目录和文件名后缀
- 🔇 **可选移除音频** - 进一步缩小文件体积
- 💾 **设置记忆** - 自动保存上次使用的设置
- 🖥️ **视频信息预览** - 显示分辨率、码率、编码、字幕流等详细信息

## 📋 系统要求

- Windows 10/11 (64位)
- 无需联网，完全离线使用
- GPU加速需要对应显卡驱动（可选）

## 🚀 快速开始

### 方式一：直接运行EXE
1. 下载 `万能视频压缩器.exe`
2. 双击运行即可使用

### 方式二：从源码构建
```bash
# 1. 安装依赖
pip install Pillow pyinstaller

# 2. 下载FFmpeg
# 从 https://www.gyan.dev/ffmpeg/builds/ 下载
# 将 ffmpeg.exe 和 ffprobe.exe 放到 assets/ffmpeg/ 目录

# 3. 运行
python main.py

# 4. 打包为EXE
# 双击 build.bat 或运行:
pyinstaller build.spec --clean --noconfirm
```

## 📖 使用说明

1. **添加文件** - 点击"+ 添加文件"选择视频，或点击"+ 添加文件夹"批量添加
2. **设置参数** - 选择分辨率、质量、编码器等
3. **高级设置** - 调节音量、设置跳过时间、加载字幕等
4. **开始压缩** - 点击"▶ 开始压缩"，等待完成

### 编码器选择
- **自动** - 自动选择最佳编码器（优先GPU）
- **NVIDIA NVENC** - NVIDIA显卡硬件加速，速度最快
- **Intel QuickSync** - Intel核显硬件加速
- **AMD AMF** - AMD显卡硬件加速
- **CPU x264** - 软件编码，兼容性最好

### 质量预设
| 预设 | CRF | 速度 | 适用场景 |
|------|-----|------|----------|
| 极速 | 28 | ultrafast | 快速预览 |
| 快速 | 26 | veryfast | 日常使用 |
| 标准 | 23 | medium | 推荐默认 |
| 高质量 | 18 | slow | 重要视频 |
| 无损 | 0 | veryslow | 存档备份 |

## 🏗️ 项目结构

```
video_compressor/
├── main.py              # 入口文件
├── gui/
│   ├── app.py           # 主窗口
│   ├── widgets.py       # 自定义控件
│   └── themes.py        # 主题配色
├── core/
│   ├── ffmpeg_engine.py # FFmpeg命令构建与执行
│   ├── hardware.py      # CPU/GPU自动检测
│   ├── subtitle.py      # 字幕处理
│   └── probe.py         # 视频信息探测
├── utils/
│   └── helpers.py       # 工具函数
├── assets/
│   ├── icon.ico         # 应用图标
│   └── ffmpeg/          # FFmpeg二进制
├── build.spec           # PyInstaller配置
├── build.bat            # Windows构建脚本
└── requirements.txt     # Python依赖
```

## 📝 许可证

本项目仅供个人学习使用。
