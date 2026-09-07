"""工具函数模块"""
import os
import sys
import json
import time
from pathlib import Path


def get_app_dir():
    """获取应用程序目录（兼容PyInstaller打包后路径）"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def get_resource_path(relative_path):
    """获取资源文件路径（兼容PyInstaller）"""
    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent.parent
    return base_path / relative_path


def format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"


def format_duration(seconds):
    """格式化时长（秒 → HH:MM:SS）"""
    if seconds is None or seconds < 0:
        return "--:--:--"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_time_remaining(seconds):
    """格式化剩余时间"""
    if seconds is None or seconds < 0:
        return "计算中..."
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}分{secs}秒"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}时{mins}分"


def get_ffmpeg_path():
    """获取FFmpeg可执行文件路径"""
    # 先检查打包资源
    ffmpeg_exe = get_resource_path(os.path.join("assets", "ffmpeg", "ffmpeg.exe"))
    if ffmpeg_exe.exists():
        return str(ffmpeg_exe)

    # 再检查应用目录下的 ffmpeg
    app_ffmpeg = get_app_dir() / "ffmpeg" / "ffmpeg.exe"
    if app_ffmpeg.exists():
        return str(app_ffmpeg)

    # 最后检查系统PATH
    return "ffmpeg"


def get_ffprobe_path():
    """获取FFprobe可执行文件路径"""
    ffprobe_exe = get_resource_path(os.path.join("assets", "ffmpeg", "ffprobe.exe"))
    if ffprobe_exe.exists():
        return str(ffprobe_exe)

    app_ffprobe = get_app_dir() / "ffmpeg" / "ffprobe.exe"
    if app_ffprobe.exists():
        return str(app_ffprobe)

    return "ffprobe"


def load_settings():
    """加载用户设置"""
    settings_file = get_app_dir() / "settings.json"
    try:
        if settings_file.exists():
            with open(settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return get_default_settings()


def save_settings(settings):
    """保存用户设置"""
    settings_file = get_app_dir() / "settings.json"
    try:
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_default_settings():
    """获取默认设置"""
    return {
        "resolution": "720p",
        "quality": "标准",
        "encoder": "auto",
        "audio_bitrate": "128k",
        "volume": 100,
        "skip_start": 0,
        "skip_end": 0,
        "subtitle_mode": "无",
        "subtitle_font_size": 24,
        "subtitle_font_color": "#FFFFFF",
        "remove_audio": False,
        "output_dir": "",
        "filename_suffix": "_720p",
        "after_complete": "无操作",
        "last_output_dir": "",
    }


SUPPORTED_VIDEO_FORMATS = [
    ("视频文件", "*.mp4;*.mkv;*.avi;*.mov;*.flv;*.wmv;*.webm;*.ts;*.m2ts;*.mpg;*.mpeg;*.3gp;*.vob;*.m4v"),
    ("MP4", "*.mp4"),
    ("MKV", "*.mkv"),
    ("AVI", "*.avi"),
    ("MOV", "*.mov"),
    ("FLV", "*.flv"),
    ("WMV", "*.wmv"),
    ("WebM", "*.webm"),
    ("TS", "*.ts"),
    ("所有文件", "*.*"),
]

SUPPORTED_SUBTITLE_FORMATS = [
    ("字幕文件", "*.srt;*.ass;*.ssa;*.sub;*.idx"),
    ("SRT字幕", "*.srt"),
    ("ASS字幕", "*.ass;*.ssa"),
    ("所有文件", "*.*"),
]

RESOLUTION_MAP = {
    "480p": {"height": 480, "crf_base": 22},
    "576p": {"height": 576, "crf_base": 22},
    "720p": {"height": 720, "crf_base": 23},
    "1080p": {"height": 1080, "crf_base": 23},
    "原始分辨率": {"height": -1, "crf_base": 23},
}

QUALITY_PRESETS = {
    "极速": {"crf": 28, "preset": "ultrafast", "audio_br": "96k"},
    "快速": {"crf": 26, "preset": "veryfast", "audio_br": "128k"},
    "标准": {"crf": 23, "preset": "medium", "audio_br": "128k"},
    "高质量": {"crf": 18, "preset": "slow", "audio_br": "192k"},
    "无损": {"crf": 0, "preset": "veryslow", "audio_br": "320k"},
}
