"""视频信息探测模块 - 使用ffprobe获取视频详细信息"""
import json
import subprocess
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from utils.helpers import get_ffprobe_path, format_file_size, format_duration

logger = logging.getLogger(__name__)


@dataclass
class SubtitleStream:
    """字幕流信息"""
    index: int
    codec: str
    language: str
    title: str
    default: bool


@dataclass
class AudioStream:
    """音频流信息"""
    index: int
    codec: str
    channels: int
    sample_rate: str
    bitrate: int
    language: str
    title: str


@dataclass
class VideoInfo:
    """视频信息"""
    file_path: str
    file_name: str
    file_size: int
    file_size_str: str
    duration: float
    duration_str: str
    format_name: str

    # 视频流
    video_codec: str = ""
    video_width: int = 0
    video_height: int = 0
    video_bitrate: int = 0
    video_fps: float = 0.0
    video_profile: str = ""

    # 音频流列表
    audio_streams: List[AudioStream] = field(default_factory=list)
    # 字幕流列表
    subtitle_streams: List[SubtitleStream] = field(default_factory=list)

    # 汇总
    has_audio: bool = False
    has_subtitle: bool = False
    resolution_str: str = ""
    estimated_output_size: str = ""

    @property
    def display_info(self) -> str:
        """用于显示的摘要信息"""
        lines = [
            f"文件: {self.file_name}",
            f"大小: {self.file_size_str}",
            f"时长: {self.duration_str}",
            f"分辨率: {self.resolution_str}",
            f"视频编码: {self.video_codec}",
            f"帧率: {self.video_fps:.2f} fps",
        ]
        if self.video_bitrate > 0:
            lines.append(f"视频码率: {self.video_bitrate // 1000} kbps")
        if self.has_audio and self.audio_streams:
            a = self.audio_streams[0]
            lines.append(f"音频: {a.codec} {a.channels}声道")
        if self.has_subtitle:
            lines.append(f"字幕流: {len(self.subtitle_streams)}个")
            for s in self.subtitle_streams:
                lang = s.language or "未知"
                title = f" - {s.title}" if s.title else ""
                lines.append(f"  [{s.index}] {s.codec} ({lang}{title})")
        return "\n".join(lines)


def probe_video(file_path: str) -> Optional[VideoInfo]:
    """探测视频文件信息"""
    import os
    try:
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)

        # 使用ffprobe获取JSON格式信息
        cmd = [
            get_ffprobe_path(),
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]

        # Windows上需要显式指定UTF-8编码以正确处理中文路径
        result = subprocess.run(
            cmd,
            capture_output=True, timeout=30,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if _is_windows() else 0
        )

        if result.returncode != 0:
            logger.error(f"ffprobe失败 (returncode={result.returncode}): {result.stderr[:500]}")
            return None

        data = json.loads(result.stdout)
        return _parse_probe_data(data, file_path, file_name, file_size)

    except subprocess.TimeoutExpired:
        logger.error("ffprobe超时")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"解析ffprobe输出失败: {e}")
        return None
    except Exception as e:
        logger.error(f"探测视频信息失败: {type(e).__name__}: {e}")
        return None


def _parse_probe_data(data: dict, file_path: str, file_name: str, file_size: int) -> VideoInfo:
    """解析ffprobe的JSON输出"""
    fmt = data.get("format", {})
    streams = data.get("streams", [])

    # 基本信息
    duration = float(fmt.get("duration", 0))
    format_name = fmt.get("format_name", "")

    info = VideoInfo(
        file_path=file_path,
        file_name=file_name,
        file_size=file_size,
        file_size_str=format_file_size(file_size),
        duration=duration,
        duration_str=format_duration(duration),
        format_name=format_name,
    )

    # 解析流信息
    for stream in streams:
        codec_type = stream.get("codec_type", "")

        if codec_type == "video" and not info.video_codec:
            # 取第一个视频流
            info.video_codec = stream.get("codec_name", "")
            info.video_width = int(stream.get("width", 0))
            info.video_height = int(stream.get("height", 0))
            info.video_profile = stream.get("profile", "")

            # 码率
            bitrate_str = stream.get("bit_rate", fmt.get("bit_rate", "0"))
            try:
                info.video_bitrate = int(bitrate_str) if bitrate_str != "N/A" else 0
            except ValueError:
                info.video_bitrate = 0

            # 帧率
            fps_str = stream.get("r_frame_rate", "0/1")
            try:
                num, den = fps_str.split("/")
                info.video_fps = float(num) / float(den) if float(den) != 0 else 0
            except (ValueError, ZeroDivisionError):
                info.video_fps = 0

            info.resolution_str = f"{info.video_width}x{info.video_height}"

        elif codec_type == "audio":
            audio = AudioStream(
                index=stream.get("index", 0),
                codec=stream.get("codec_name", ""),
                channels=int(stream.get("channels", 0)),
                sample_rate=stream.get("sample_rate", ""),
                bitrate=int(stream.get("bit_rate", 0) or 0),
                language=stream.get("tags", {}).get("language", ""),
                title=stream.get("tags", {}).get("title", ""),
            )
            info.audio_streams.append(audio)

        elif codec_type == "subtitle":
            sub = SubtitleStream(
                index=stream.get("index", 0),
                codec=stream.get("codec_name", ""),
                language=stream.get("tags", {}).get("language", ""),
                title=stream.get("tags", {}).get("title", ""),
                default=stream.get("disposition", {}).get("default", 0) == 1,
            )
            info.subtitle_streams.append(sub)

    info.has_audio = len(info.audio_streams) > 0
    info.has_subtitle = len(info.subtitle_streams) > 0

    return info


def _is_windows():
    import sys
    return sys.platform == "win32"
