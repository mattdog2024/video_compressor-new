"""字幕处理模块 - 提取内置字幕、处理外挂字幕"""
import os
import re
import subprocess
import tempfile
import logging
from typing import Optional, List

from utils.helpers import get_ffmpeg_path

logger = logging.getLogger(__name__)

# 文本字幕可交给 libass 的 subtitles 滤镜直接从容器中读取；图片字幕必须
# 解码为图像后再叠到视频上，不能错误地转为 SRT。
BITMAP_SUBTITLE_CODECS = frozenset({
    "hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub",
})

_ASS_OVERRIDE_BLOCK = re.compile(r"\{\\[^}]*\}")
_HTML_STYLE_TAG = re.compile(r"</?(?:font|b|i|u|s|span)(?:\s+[^>]*)?>", re.IGNORECASE)


def clean_text_subtitle_content(content: str) -> str:
    """清掉 ASS/HTML 样式覆盖，只保留可读文字和时间轴。"""
    clean = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    clean = _ASS_OVERRIDE_BLOCK.sub("", clean)
    clean = _HTML_STYLE_TAG.sub("", clean)
    clean = clean.replace(r"\N", "\n").replace(r"\n", "\n")
    # 部分 ASS 转 SRT 时会留下行尾反斜杠；去掉它避免显示成乱码。
    clean = re.sub(r"\\\n", "\n", clean)
    return clean


def prepare_clean_embedded_text_subtitle(input_file: str, stream_index: int,
                                         output_dir: str = None) -> Optional[str]:
    """导出内置文字字幕并剥离原片复杂的字号、模糊、位置等样式。"""
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="video_compressor_subtitle_")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "clean_embedded_subtitle.srt")

    cmd = [
        get_ffmpeg_path(), "-y", "-i", input_file,
        "-map", f"0:{stream_index}", "-c:s", "srt", output_file,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if _is_windows() else 0,
        )
        if result.returncode != 0 or not os.path.exists(output_file):
            logger.warning("文字内置字幕标准化失败: %s", result.stderr[-500:])
            return None
        with open(output_file, "r", encoding="utf-8-sig") as subtitle_file:
            clean = clean_text_subtitle_content(subtitle_file.read())
        with open(output_file, "w", encoding="utf-8") as subtitle_file:
            subtitle_file.write(clean)
        return output_file
    except Exception as exc:
        logger.warning("文字内置字幕标准化异常: %s", exc)
        return None


def subtitle_kind_label(codec: str) -> str:
    """返回给界面显示的字幕类型，避免用户只看到难懂的编码名。"""
    normalized = (codec or "").lower()
    if normalized == "hdmv_pgs_subtitle":
        return "PGS 图片字幕"
    if normalized in {"dvd_subtitle", "dvb_subtitle", "xsub"}:
        return "图片字幕"
    if normalized in {"ass", "ssa"}:
        return "ASS 样式字幕"
    if normalized in {"subrip", "srt", "mov_text", "webvtt", "text"}:
        return "文字字幕"
    return f"{codec or '未知'} 字幕"


def format_subtitle_choice(file_name: str, ordinal: int, stream_index: int,
                           codec: str, language: str = "", title: str = "",
                           is_default: bool = False) -> tuple[str, str]:
    """生成简短下拉项和可换行的完整字幕信息。"""
    language_label = language or "未标语言"
    kind = subtitle_kind_label(codec)
    short_label = f"第{ordinal + 1}条 · {language_label} · {kind}"
    default_label = "默认字幕" if is_default else "普通字幕"
    title_label = title or "未标注标题"
    detail = (
        f"文件：{file_name}\n"
        f"字幕：第{ordinal + 1}条（流 #{stream_index}）· {kind} · {language_label} · {default_label}\n"
        f"完整名称：{title_label}"
    )
    return short_label, detail


def select_embedded_subtitle_stream(streams, selected_stream_index: Optional[int] = None):
    """从一个视频自己的字幕流中选轨道，不允许跨文件借用选择。"""
    if not streams:
        return None
    if selected_stream_index is not None:
        selected = next(
            (stream for stream in streams if stream.index == selected_stream_index),
            None,
        )
        if selected is not None:
            return selected
    return next((stream for stream in streams if stream.default), streams[0])


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


def is_bitmap_subtitle_codec(codec: str) -> bool:
    """判断内置字幕是否是需要图像叠加的位图字幕。"""
    return (codec or "").lower() in BITMAP_SUBTITLE_CODECS


def _escape_filter_path(path: str) -> str:
    """转义 FFmpeg filter 中的文件路径，兼容 Windows 盘符和中文路径。"""
    return path.replace("\\", "/").replace("'", r"\'").replace(":", r"\:")


def build_subtitle_filter(subtitle_path: str, font_size: int = 24,
                          font_color: str = "white",
                          outline_color: str = "#000000",
                          margin_v: int = 30,
                          stream_ordinal: int = -1) -> str:
    """构建字幕烧录的video filter字符串"""
    # 处理路径中的特殊字符（Windows路径反斜杠和冒号需要转义）
    escaped_path = _escape_filter_path(subtitle_path)

    # 构建force_style
    style_parts = [
        "FontName=Microsoft YaHei",
        f"FontSize={font_size}",
        f"PrimaryColour=&H00{font_color_to_bgr(font_color)}",
        f"OutlineColour=&H00{font_color_to_bgr(outline_color)}",
        "Bold=0",
        "Outline=2",
        "Shadow=0",
        "Alignment=2",
        f"MarginV={margin_v}",
    ]
    force_style = ",".join(style_parts)

    filter_parts = [f"filename='{escaped_path}'"]
    if stream_ordinal >= 0:
        filter_parts.append(f"si={stream_ordinal}")
    filter_parts.append(f"force_style='{force_style}'")
    return "subtitles=" + ":".join(filter_parts)


def build_embedded_subtitle_filter(video_path: str, stream_ordinal: int,
                                   font_size: int = 24,
                                   font_color: str = "#FFFFFF") -> str:
    """构建文本内置字幕的直接烧录滤镜，不经过临时 SRT 文件。"""
    return build_subtitle_filter(
        video_path,
        font_size=font_size,
        font_color=font_color,
        stream_ordinal=stream_ordinal,
    )


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
