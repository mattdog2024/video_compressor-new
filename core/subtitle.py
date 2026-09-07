"""字幕处理模块 - 提取内置字幕、处理外挂字幕"""
import os
import subprocess
import tempfile
import logging
from typing import Optional, List

from utils.helpers import get_ffmpeg_path

logger = logging.getLogger(__name__)


def extract_subtitle(input_file: str, stream_index: int, output_dir: str = None) -> Optional[str]:
    """从视频中提取字幕流为SRT文件"""
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(output_dir, f"{base_name}_sub_{stream_index}.srt")

    cmd = [
        get_ffmpeg_path(),
        "-y",
        "-i", input_file,
        "-map", f"0:{stream_index}",
        "-c:s", "srt",
        output_file
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if _is_windows() else 0
        )

        if result.returncode == 0 and os.path.exists(output_file):
            logger.info(f"字幕提取成功: {output_file}")
            return output_file
        else:
            logger.error(f"字幕提取失败: {result.stderr}")
            return None

    except Exception as e:
        logger.error(f"提取字幕异常: {e}")
        return None


def convert_subtitle_to_srt(input_file: str, output_dir: str = None) -> Optional[str]:
    """将字幕文件转换为SRT格式（如果需要）"""
    ext = os.path.splitext(input_file)[1].lower()

    if ext in ('.srt',):
        return input_file  # 已经是SRT

    if output_dir is None:
        output_dir = tempfile.gettempdir()

    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(output_dir, f"{base_name}_converted.srt")

    cmd = [
        get_ffmpeg_path(),
        "-y",
        "-i", input_file,
        output_file
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if _is_windows() else 0
        )

        if result.returncode == 0 and os.path.exists(output_file):
            return output_file
        return None

    except Exception as e:
        logger.error(f"转换字幕格式失败: {e}")
        return None


def build_subtitle_filter(subtitle_path: str, font_size: int = 24,
                          font_color: str = "white",
                          outline_color: str = "black",
                          margin_v: int = 30) -> str:
    """构建字幕烧录的video filter字符串"""
    # 处理路径中的特殊字符（Windows路径反斜杠和冒号需要转义）
    escaped_path = subtitle_path.replace("\\", "/").replace(":", "\\:")

    # 构建force_style
    style_parts = [
        f"FontSize={font_size}",
        f"PrimaryColour=&H00{font_color_to_bgr(font_color)}",
        f"OutlineColour=&H00{font_color_to_bgr(outline_color)}",
        "Outline=2",
        f"MarginV={margin_v}",
    ]
    force_style = ",".join(style_parts)

    return f"subtitles='{escaped_path}':force_style='{force_style}'"


def font_color_to_bgr(hex_color: str) -> str:
    """将十六进制颜色转换为ASS格式的BGR（去#号）"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"{b}{g}{r}"
    return "FFFFFF"


def get_subtitle_filter_for_external(subtitle_path: str, font_size: int = 24,
                                     font_color: str = "#FFFFFF") -> str:
    """为外挂字幕构建滤镜"""
    # 先转换格式（如果需要）
    srt_path = convert_subtitle_to_srt(subtitle_path)
    if srt_path is None:
        srt_path = subtitle_path
    return build_subtitle_filter(srt_path, font_size, font_color)
