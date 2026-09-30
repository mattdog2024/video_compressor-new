"""FFmpeg引擎 - 构建命令、执行压缩、解析进度"""
import os
import re
import math
import subprocess
import threading
import time
import logging
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from typing import Optional, Callable, List
from enum import Enum

from utils.helpers import (
    get_ffmpeg_path, get_handbrake_path, handbrake_available,
    RESOLUTION_MAP, QUALITY_PRESETS,
)
from core.subtitle import (
    build_embedded_subtitle_filter, build_subtitle_filter,
    get_subtitle_filter_for_external, is_bitmap_subtitle_codec,
    prepare_clean_embedded_text_subtitle, has_bilingual_subtitles,
)

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CompressTask:
    """压缩任务"""
    task_id: int
    input_file: str
    output_file: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    speed: str = ""
    elapsed_time: float = 0.0
    remaining_time: Optional[float] = None
    error_message: str = ""
    output_size: int = 0
    fallback_note: str = ""


@dataclass
class CompressOptions:
    """压缩选项"""
    resolution: str = "720p"
    quality: str = "标准"
    encoder: str = "auto"
    custom_crf: int = 23
    custom_preset: str = "medium"
    audio_bitrate: str = "128k"
    volume: int = 100          # 0-100
    skip_start: float = 0      # 跳过开头秒数
    skip_end: float = 0        # 跳过结尾秒数
    remove_audio: bool = False
    subtitle_mode: str = "none"  # none / embedded / external
    subtitle_stream_index: int = -1
    subtitle_stream_ordinal: int = -1
    subtitle_codec: str = ""
    subtitle_canvas_width: int = 0
    subtitle_canvas_height: int = 0
    external_subtitle_path: str = ""
    subtitle_font_size: int = 24
    subtitle_font_color: str = "#FFFFFF"
    subtitle_bilingual: bool = False  # 自动检测到中英双语时减少占屏
    gpu_encoder: str = ""        # 具体GPU编码器名
    platform_compatibility: bool = True  # 主流平台兼容：H.264 8位 + AAC-LC 48k
    extra_args: List[str] = field(default_factory=list)


class FFmpegEngine:
    """FFmpeg处理引擎"""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._cancelled = False
        self._paused = False
        self._on_progress: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        self._current_task: Optional[CompressTask] = None
        self._start_time: float = 0
        self._temporary_subtitle_dirs: List[str] = []

    @staticmethod
    def _uses_bitmap_subtitle_backend(options: CompressOptions) -> bool:
        """图片字幕必须交给 HandBrake 原生渲染器处理。"""
        return (
            options.subtitle_mode == "embedded"
            and options.subtitle_stream_ordinal >= 0
            and is_bitmap_subtitle_codec(options.subtitle_codec)
        )

    @staticmethod
    def _handbrake_encoder_name(encoder_name: str) -> str:
        """将现有的编码器选择映射为 HandBrakeCLI 名称。"""
        return {
            "h264_nvenc": "nvenc_h264",
            "h264_qsv": "qsv_h264",
            "h264_amf": "vce_h264",
            "libx264": "x264",
        }.get(encoder_name, "x264")

    def build_handbrake_command(self, task: CompressTask, options: CompressOptions,
                                total_duration: float = 0,
                                source_height: int = 0) -> list:
        """构建 PGS/DVB/VobSub 图片字幕的 HandBrake 原生烧录命令。"""
        encoder_name = self._resolve_encoder(options)
        if options.platform_compatibility:
            encoder_name = self._get_platform_compatible_encoder(encoder_name)
        handbrake_encoder = self._handbrake_encoder_name(encoder_name)
        quality_config = QUALITY_PRESETS.get(options.quality, QUALITY_PRESETS["标准"])

        cmd = [
            get_handbrake_path(),
            "-i", task.input_file,
            "-o", task.output_file,
            "--format", "av_mp4",
            "--optimize",
            "--crop", "0:0:0:0",
            "--encoder", handbrake_encoder,
            "--subtitle", str(options.subtitle_stream_ordinal + 1),
            "--subtitle-burned=1",
        ]

        # 不放大低分辨率片源；对指定分辨率采用 HandBrake 原生缩放。
        target_height = RESOLUTION_MAP.get(options.resolution, RESOLUTION_MAP["720p"])["height"]
        if target_height > 0 and (source_height <= 0 or source_height > target_height):
            cmd.extend(["--width", "0", "--height", str(target_height)])

        if options.quality == "极速":
            target_rate = int(self._fast_nvenc_target_rate(options.resolution, source_height).rstrip("k"))
            # 图片字幕走 HandBrake 的平均码率模式，和极速 NVENC 使用同一档位，
            # 让长片不会糊成马赛克也不会无上限变大。
            cmd.extend(["--vb", str(target_rate), "--no-multi-pass"])
            if handbrake_encoder == "x264":
                cmd.extend(["--encoder-preset", "veryfast"])
            else:
                cmd.extend(["--encoder-preset", "fast"])
        else:
            cmd.extend(["--quality", str(quality_config["crf"])])
            if handbrake_encoder == "x264":
                cmd.extend(["--encoder-preset", quality_config["preset"]])

        if options.remove_audio:
            cmd.extend(["--audio", "none"])
        else:
            audio_br = quality_config["audio_br"] if options.quality == "极速" else options.audio_bitrate
            cmd.extend(["--audio", "1", "--aencoder", "av_aac", "--ab", audio_br.rstrip("k")])
            if options.volume != 100:
                # HandBrake 的 gain 使用 dB；与 FFmpeg 的 volume 比例语义对应。
                volume_factor = max(0.01, options.volume / 100.0)
                gain_db = 20 * math.log10(volume_factor)
                cmd.extend(["--gain", f"{gain_db:.2f}"])

        if options.skip_start > 0:
            cmd.extend(["--start-at", f"duration:{options.skip_start}"])
        if total_duration > 0 and options.skip_end > 0:
            encode_duration = total_duration - options.skip_start - options.skip_end
            if encode_duration > 0:
                cmd.extend(["--stop-at", f"duration:{encode_duration}"])

        return cmd

    def build_command(self, task: CompressTask, options: CompressOptions,
                      total_duration: float = 0,
                      source_height: int = 0) -> list:
        """构建FFmpeg命令"""
        cmd = [get_ffmpeg_path()]

        # PGS/VobSub 是带坐标的图片字幕。修复没有明确结束时间的字幕包，
        # 否则 FFmpeg 会把它当成一瞬间的空图层，表现为“压完没有字幕”。
        is_bitmap_embedded = (
            options.subtitle_mode == "embedded"
            and options.subtitle_stream_ordinal >= 0
            and is_bitmap_subtitle_codec(options.subtitle_codec)
        )
        if is_bitmap_embedded:
            # 部分 PGS 的字幕画布高度会大于实际电影画面（如影片 1280×692、
            # 字幕画布 1280×720）。把原始画布传给解码器，避免它把带坐标的
            # 图片字幕解成空图层或错位到屏幕外。
            if options.subtitle_canvas_width > 0 and options.subtitle_canvas_height > 0:
                cmd.extend([
                    "-canvas_size",
                    f"{options.subtitle_canvas_width}x{options.subtitle_canvas_height}",
                ])
            cmd.append("-fix_sub_duration")

        # 跳过开头
        if options.skip_start > 0:
            cmd.extend(["-ss", str(options.skip_start)])

        cmd.extend(["-i", task.input_file])

        # 计算结束时间
        end_time = None
        if total_duration > 0 and options.skip_end > 0:
            end_time = total_duration - options.skip_end
            if options.skip_start > 0:
                end_time -= options.skip_start
            if end_time <= 0:
                end_time = None

        # === 视频滤镜 ===
        vf_parts = []

        # 缩放（不放大：如果源分辨率小于目标分辨率，保持原始分辨率）
        res_config = RESOLUTION_MAP.get(options.resolution, RESOLUTION_MAP["720p"])
        height = res_config["height"]
        if height > 0:
            if source_height > 0 and source_height <= height:
                # 源分辨率已经小于等于目标，不放大，只确保偶数
                vf_parts.append(f"scale=trunc(iw/2)*2:trunc(ih/2)*2")
            else:
                vf_parts.append(f"scale=-2:{height}")

        # 字幕滤镜
        bitmap_subtitle_ordinal = -1
        subtitle_is_bilingual = options.subtitle_bilingual
        if options.subtitle_mode == "external" and options.external_subtitle_path:
            subtitle_is_bilingual = subtitle_is_bilingual or has_bilingual_subtitles(
                options.external_subtitle_path,
            )
        text_subtitle_font_size = self._effective_text_subtitle_font_size(
            options.subtitle_font_size, options.resolution, source_height,
            subtitle_is_bilingual,
        )
        if options.subtitle_mode == "embedded" and options.subtitle_stream_index >= 0:
            # 文本字幕直接从原视频容器读取，避免临时转 SRT 造成失败或乱码。
            # PGS/VobSub 等图片字幕必须由滤镜图叠加，不能转成文本字幕。
            if is_bitmap_subtitle_codec(options.subtitle_codec):
                bitmap_subtitle_ordinal = options.subtitle_stream_ordinal
            elif options.subtitle_stream_ordinal >= 0:
                vf_parts.append(build_embedded_subtitle_filter(
                    task.input_file,
                    options.subtitle_stream_ordinal,
                    text_subtitle_font_size,
                    options.subtitle_font_color,
                ))
        elif options.subtitle_mode == "external" and options.external_subtitle_path:
            sub_filter = get_subtitle_filter_for_external(
                options.external_subtitle_path,
                text_subtitle_font_size,
                options.subtitle_font_color
            )
            vf_parts.append(sub_filter)

        # === 视频编码 ===
        encoder_name = self._resolve_encoder(options)
        if options.platform_compatibility:
            encoder_name = self._get_platform_compatible_encoder(encoder_name)

        if bitmap_subtitle_ordinal >= 0:
            # 图片字幕（PGS/VobSub）是一整张带透明边的定位画布，不是只有文字的
            # 小图片。把整张画布再放大并贴右下，会改变它的坐标，可能直接把字幕
            # 推到画面外，结果是“压完没有字幕”。先按视频参考画布直接叠加，再把
            # 已叠好的画面整体缩放，才能保留原片字幕的位置和显示时长。
            video_filters = ",".join(vf_parts) if vf_parts else "null"
            filter_complex = (
                "[0:v:0]setpts=PTS-STARTPTS[vsrc];"
                f"[0:s:{bitmap_subtitle_ordinal}]setpts=PTS-STARTPTS[ssrc];"
                "[ssrc][vsrc]scale2ref[subs][vbase];"
                # 图片字幕通常只在开始和清除时各给一帧，必须保留开始帧到下一张
                # 透明清除帧，否则用户会看到“压制成功但字幕一闪而过/完全没显示”。
                "[vbase][subs]overlay=shortest=0:eof_action=pass:repeatlast=1:"
                "alpha=straight:format=auto[burned];"
                f"[burned]{video_filters}[vout]"
            )
            cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]"])
        else:
            if vf_parts:
                cmd.extend(["-vf", ",".join(vf_parts)])
            cmd.extend(["-map", "0:v:0"])

        # 明确只保留首条音频，避免内置字幕烧录后又把字幕流写进 MP4。
        cmd.extend(["-map", "0:a:0?"])

        # 编码器参数
        quality_config = QUALITY_PRESETS.get(options.quality, QUALITY_PRESETS["标准"])

        if encoder_name in ("h264_nvenc", "hevc_nvenc"):
            # NVIDIA NVENC
            crf = quality_config["crf"]
            cq_value = max(0, min(51, crf))
            cmd.extend(["-c:v", encoder_name])
            # “极速”仍优先吞吐量，但不能把三小时影片压到明显起色块的码率。
            rate_control = "vbr" if options.quality == "极速" else "vbr_hq"
            preset = "p2" if options.quality == "极速" else "p4"
            cmd.extend(["-rc", rate_control])
            cmd.extend(["-cq", str(cq_value)])
            cmd.extend(["-preset", preset])
            if options.quality == "极速":
                # 极速模式曾设置 -b:v 0，CQ 会无限追画质，长片即使压到 480p
                # 仍可能比原压缩包大；后来 400k 又过度压缩。按实际输出高度给
                # VBR 合理的目标和上限，保留清晰度同时避免无限膨胀。
                target_rate = self._fast_nvenc_target_rate(options.resolution, source_height)
                target_kbps = int(target_rate.rstrip("k"))
                max_rate = ((target_kbps * 4 // 3 + 99) // 100) * 100
                cmd.extend([
                    "-b:v", target_rate,
                    "-maxrate", f"{max_rate}k",
                    "-bufsize", f"{int(target_rate.rstrip('k')) * 2}k",
                ])
            else:
                cmd.extend(["-b:v", "0"])
        elif encoder_name in ("h264_qsv", "hevc_qsv"):
            # Intel QuickSync
            crf = quality_config["crf"]
            cmd.extend(["-c:v", encoder_name])
            cmd.extend(["-global_quality", str(crf)])
            qsv_preset = "veryfast" if options.quality == "极速" else quality_config["preset"]
            cmd.extend(["-preset", qsv_preset])
        elif encoder_name in ("h264_amf", "hevc_amf"):
            # AMD AMF
            crf = quality_config["crf"]
            cmd.extend(["-c:v", encoder_name])
            cmd.extend(["-rc", "cqp"])
            cmd.extend(["-qp_i", str(crf)])
            cmd.extend(["-qp_p", str(crf)])
            cmd.extend(["-qp_b", str(crf + 2)])
        else:
            # CPU libx264/libx265
            crf = options.custom_crf if options.quality == "自定义" else quality_config["crf"]
            preset = options.custom_preset if options.quality == "自定义" else quality_config["preset"]
            cmd.extend(["-c:v", encoder_name])
            cmd.extend(["-crf", str(crf)])
            cmd.extend(["-preset", preset])
            if options.quality != "极速":
                cmd.extend(["-tune", "film"])

        # 不少上传平台不支持 10 位 H.264（High 10），即使Windows播放器能够播放。
        # 使用 Main + yuv420p 可确保输出为常见的 8 位 H.264 MP4。
        if options.platform_compatibility:
            cmd.extend(["-profile:v", "main"])
            cmd.extend(["-pix_fmt", "yuv420p"])

        # === 音频 ===
        if options.remove_audio:
            cmd.extend(["-an"])
        else:
            cmd.extend(["-c:a", "aac"])
            # 极速模式必须连音频一起降到预设码率；旧代码错误地一直沿用128k。
            audio_br = quality_config["audio_br"] if options.quality == "极速" else options.audio_bitrate
            cmd.extend(["-b:a", audio_br])
            cmd.extend(["-ac", "2"])  # 立体声
            if options.platform_compatibility:
                # AAC-LC / 48kHz 是主流视频平台最稳妥的音频组合。
                cmd.extend(["-profile:a", "aac_low", "-ar", "48000"])

            # 音量调节
            if options.volume != 100:
                vol_factor = options.volume / 100.0
                cmd.extend(["-af", f"volume={vol_factor:.2f}"])

        # 结束时间
        if end_time is not None:
            cmd.extend(["-to", str(end_time)])

        # 输出优化
        cmd.extend(["-movflags", "+faststart"])

        # 额外参数
        cmd.extend(options.extra_args)

        # 进度输出
        cmd.extend(["-progress", "pipe:1", "-nostats"])

        # 输出文件
        cmd.extend(["-y", task.output_file])

        return cmd

    @staticmethod
    def _bitmap_subtitle_scale_factor(resolution: str, source_height: int) -> float:
        """按实际输出高度放大图片字幕，目标是不低于约 960p 的阅读大小。"""
        target_height = RESOLUTION_MAP.get(
            resolution, RESOLUTION_MAP["720p"]
        )["height"]
        if target_height > 0:
            # 本程序不会放大低分辨率视频，字幕应以实际输出高度而非用户选择的
            # 更高分辨率计算倍率。
            effective_height = min(source_height, target_height) if source_height > 0 else target_height
        else:
            effective_height = source_height

        if effective_height <= 0 or effective_height >= 960:
            return 1.0
        return min(2.0, max(1.0, 960.0 / effective_height))

    @staticmethod
    def _effective_text_subtitle_font_size(requested_size: int, resolution: str,
                                           source_height: int,
                                           is_bilingual: bool = False) -> int:
        """给文字字幕设定随最终输出高度和语种数量变化的最低可读字号。"""
        requested_size = max(1, int(requested_size or 24))
        target_height = RESOLUTION_MAP.get(
            resolution, RESOLUTION_MAP["720p"]
        )["height"]
        if target_height > 0:
            effective_height = min(source_height, target_height) if source_height > 0 else target_height
        else:
            effective_height = source_height
        if effective_height <= 0:
            return requested_size

        # 干净 SRT 已不受原 ASS 的 \fs 样式干扰。480p 单语使用 28；
        # 中英双语通常至少两行，使用 26 降低对画面的遮挡。用户主动填更大值优先。
        single_language_minimum = min(48, max(28, round(effective_height * 0.05)))
        readable_minimum = max(24, single_language_minimum - 2) if is_bilingual else single_language_minimum
        return max(requested_size, readable_minimum)

    @staticmethod
    def _fast_nvenc_target_rate(resolution: str, source_height: int) -> str:
        """为极速 NVENC 按最终输出高度提供稳定的小体积目标视频码率。"""
        target_height = RESOLUTION_MAP.get(
            resolution, RESOLUTION_MAP["720p"]
        )["height"]
        if target_height > 0:
            effective_height = min(source_height, target_height) if source_height > 0 else target_height
        else:
            effective_height = source_height

        if effective_height <= 480:
            return "900k"
        if effective_height <= 576:
            return "900k"
        if effective_height <= 720:
            return "1400k"
        if effective_height <= 1080:
            return "3000k"
        return "5000k"

    def _resolve_encoder(self, options: CompressOptions) -> str:
        """解析编码器选择"""
        if options.encoder == "auto":
            if options.gpu_encoder:
                return options.gpu_encoder
            return "libx264"
        return options.encoder

    @staticmethod
    def _get_platform_compatible_encoder(encoder_name: str) -> str:
        """将H.265或未知编码选择安全地收敛到平台通用的H.264。"""
        compatible_encoders = {
            "h264_nvenc", "h264_qsv", "h264_amf", "libx264",
        }
        h265_to_h264 = {
            "hevc_nvenc": "h264_nvenc",
            "hevc_qsv": "h264_qsv",
            "hevc_amf": "h264_amf",
            "libx265": "libx264",
        }
        if encoder_name in compatible_encoders:
            return encoder_name
        return h265_to_h264.get(encoder_name, "libx264")

    def start_task(self, task: CompressTask, options: CompressOptions,
                   total_duration: float = 0,
                   source_height: int = 0,
                   on_progress: Callable = None,
                   on_complete: Callable = None,
                   on_error: Callable = None):
        """启动压缩任务"""
        self._current_task = task
        self._cancelled = False
        self._paused = False
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        self._start_time = time.time()

        prepared_options = self._prepare_text_subtitle_options(task, options)

        if self._uses_bitmap_subtitle_backend(prepared_options):
            if not handbrake_available():
                task.status = TaskStatus.FAILED
                task.error_message = (
                    "图片字幕（PGS/DVB/VobSub）需要 HandBrake 原生烧录组件，"
                    "但当前发布包里未找到 HandBrakeCLI。请下载最新版压缩器后重试。"
                )
                if self._on_error:
                    self._on_error(task)
                return
            cmd = self.build_handbrake_command(
                task, prepared_options, total_duration, source_height=source_height,
            )
            logger.info("HandBrake图片字幕烧录命令: %s", " ".join(cmd))
            run_target = self._run_handbrake_process
        else:
            cmd = self.build_command(task, prepared_options, total_duration, source_height=source_height)
            logger.info("FFmpeg命令: %s", " ".join(cmd))
            run_target = self._run_process

        task.status = TaskStatus.RUNNING

        self._thread = threading.Thread(
            target=run_target,
            args=(cmd, task, total_duration, prepared_options, source_height),
            daemon=True
        )
        self._thread.start()

    def _prepare_text_subtitle_options(self, task: CompressTask,
                                       options: CompressOptions) -> CompressOptions:
        """把内置文字字幕变成干净 SRT，禁止原片样式把文字烧糊。"""
        if (
            options.subtitle_mode != "embedded"
            or options.subtitle_stream_index < 0
            or is_bitmap_subtitle_codec(options.subtitle_codec)
        ):
            return options

        temp_dir = tempfile.mkdtemp(prefix="video_compressor_subtitle_")
        clean_subtitle = prepare_clean_embedded_text_subtitle(
            task.input_file, options.subtitle_stream_index, temp_dir,
        )
        if not clean_subtitle:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.warning("无法标准化内置文字字幕，保留原始字幕烧录路径")
            return options

        self._temporary_subtitle_dirs.append(temp_dir)
        logger.info("内置文字字幕已标准化: %s", clean_subtitle)
        return replace(
            options,
            subtitle_mode="external",
            external_subtitle_path=clean_subtitle,
            subtitle_bilingual=has_bilingual_subtitles(clean_subtitle),
        )

    def _cleanup_temporary_subtitles(self):
        """删除本任务生成的临时标准字幕。"""
        for directory in self._temporary_subtitle_dirs:
            shutil.rmtree(directory, ignore_errors=True)
        self._temporary_subtitle_dirs.clear()

    def _execute_process(self, cmd: list, task: CompressTask,
                         total_duration: float) -> tuple[int, str]:
        """执行一次FFmpeg命令，并完整收集错误输出。"""
        stderr_output = []

        def _drain_stderr():
            """后台读取stderr，防止管道缓冲区填满导致FFmpeg阻塞"""
            try:
                if self._process.stderr:
                    for line in self._process.stderr:
                        stderr_output.append(line)
            except Exception:
                pass

        creation_flags = 0
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NO_WINDOW

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            errors='replace',
            creationflags=creation_flags
        )

        # 启动stderr后台读取线程，防止管道缓冲区填满导致FFmpeg阻塞
        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # 解析进度
        self._parse_progress(self._process, task, total_duration)

        # 等待进程和stderr读取线程完成，避免遗漏真正的失败原因
        self._process.wait()
        stderr_thread.join(timeout=2)
        return self._process.returncode, "".join(stderr_output)

    def _execute_handbrake_process(self, cmd: list, task: CompressTask,
                                   total_duration: float) -> tuple[int, str]:
        """执行 HandBrakeCLI 并把百分比进度转换为界面任务进度。"""
        output_lines = []
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
        )
        progress_pattern = re.compile(r"Encoding:\s*task\s+\d+\s+of\s+\d+,\s*([\d.]+)\s*%")
        for line in self._process.stdout or []:
            output_lines.append(line)
            match = progress_pattern.search(line)
            if match:
                try:
                    task.progress = min(99.0, max(0.0, float(match.group(1))))
                    task.elapsed_time = time.time() - self._start_time
                    if task.progress > 0 and total_duration > 0:
                        elapsed = max(0.001, task.elapsed_time)
                        encoded_seconds = total_duration * task.progress / 100.0
                        task.speed = f"{encoded_seconds / elapsed:.1f}x"
                        task.remaining_time = elapsed * (100.0 - task.progress) / task.progress
                    if self._on_progress:
                        self._on_progress(task)
                except ValueError:
                    pass
        self._process.wait()
        return self._process.returncode, "".join(output_lines)

    @staticmethod
    def _is_gpu_encoder(encoder_name: str) -> bool:
        """判断编码器是否依赖显卡硬件。"""
        return encoder_name in {
            "h264_nvenc", "hevc_nvenc",
            "h264_qsv", "hevc_qsv",
            "h264_amf", "hevc_amf",
        }

    @staticmethod
    def _format_error(stderr_output: str) -> str:
        """提取对用户有用的FFmpeg错误信息。"""
        lines = [line.strip() for line in stderr_output.splitlines() if line.strip()]
        if not lines:
            return "未知错误"

        # 驱动/API 不兼容等根因通常在前面，优先保留这些行。
        important_words = (
            "Driver does not support", "minimum required", "Cannot load",
            "No capable devices", "No NVENC capable", "Error while opening encoder",
        )
        important = [line for line in lines if any(word in line for word in important_words)]
        selected = important or lines[-8:]
        return "\n".join(selected)[-1000:]

    def _complete_task(self, task: CompressTask):
        """标记任务成功并通知界面。"""
        task.status = TaskStatus.COMPLETED
        task.progress = 100.0
        if os.path.exists(task.output_file):
            task.output_size = os.path.getsize(task.output_file)
        if self._on_complete:
            self._on_complete(task)

    def _run_process(self, cmd: list, task: CompressTask, total_duration: float,
                     options: CompressOptions, source_height: int):
        """在后台线程中运行FFmpeg；GPU不可用时自动改用CPU。"""
        try:
            returncode, stderr_output = self._execute_process(cmd, task, total_duration)

            if self._cancelled:
                task.status = TaskStatus.CANCELLED
                return

            if returncode == 0:
                self._complete_task(task)
                return

            # 显卡驱动、GPU占用或运行库变化可能让已检测到的GPU编码器失效。
            # 此时自动用CPU重试一次，避免用户只看到难懂的“encoder before EOF”。
            if self._is_gpu_encoder(self._resolve_encoder(options)):
                gpu_error = self._format_error(stderr_output)
                task.fallback_note = "GPU编码不可用，已自动改用CPU编码"
                logger.warning("%s；改用 libx264 重试", gpu_error)
                task.progress = 0.0
                task.speed = ""
                task.remaining_time = None
                if self._on_progress:
                    self._on_progress(task)

                fallback_options = replace(options, encoder="libx264", gpu_encoder="")
                fallback_cmd = self.build_command(
                    task, fallback_options, total_duration, source_height
                )
                returncode, fallback_stderr = self._execute_process(
                    fallback_cmd, task, total_duration
                )
                if self._cancelled:
                    task.status = TaskStatus.CANCELLED
                    return
                if returncode == 0:
                    self._complete_task(task)
                    return
                fallback_error = self._format_error(fallback_stderr)
                task.status = TaskStatus.FAILED
                task.error_message = (
                    f"GPU编码失败：\n{gpu_error}\n\nCPU重试也失败：\n{fallback_error}"
                )[-1000:]
                if self._on_error:
                    self._on_error(task)
                return

            task.status = TaskStatus.FAILED
            task.error_message = self._format_error(stderr_output)
            if self._on_error:
                self._on_error(task)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            if self._on_error:
                self._on_error(task)
        finally:
            self._cleanup_temporary_subtitles()

    def _run_handbrake_process(self, cmd: list, task: CompressTask, total_duration: float,
                               options: CompressOptions, source_height: int):
        """运行图片字幕原生烧录；硬件编码失败时用 CPU 自动重试一次。"""
        try:
            returncode, output = self._execute_handbrake_process(cmd, task, total_duration)
            if self._cancelled:
                task.status = TaskStatus.CANCELLED
                return
            if returncode == 0:
                self._complete_task(task)
                return

            encoder = self._resolve_encoder(options)
            if self._is_gpu_encoder(encoder):
                gpu_error = self._format_error(output)
                task.fallback_note = "图片字幕硬件编码不可用，已自动改用CPU编码"
                logger.warning("HandBrake图片字幕硬件编码失败：%s；改用 x264 重试", gpu_error)
                try:
                    if os.path.exists(task.output_file):
                        os.remove(task.output_file)
                except OSError:
                    pass
                task.progress = 0.0
                task.speed = ""
                task.remaining_time = None
                if self._on_progress:
                    self._on_progress(task)
                fallback_options = replace(options, encoder="libx264", gpu_encoder="")
                fallback_cmd = self.build_handbrake_command(
                    task, fallback_options, total_duration, source_height,
                )
                returncode, fallback_output = self._execute_handbrake_process(
                    fallback_cmd, task, total_duration,
                )
                if self._cancelled:
                    task.status = TaskStatus.CANCELLED
                    return
                if returncode == 0:
                    self._complete_task(task)
                    return
                task.status = TaskStatus.FAILED
                task.error_message = (
                    f"图片字幕硬件编码失败：\n{gpu_error}\n\nCPU重试也失败：\n"
                    f"{self._format_error(fallback_output)}"
                )[-1000:]
            else:
                task.status = TaskStatus.FAILED
                task.error_message = self._format_error(output)
            if self._on_error:
                self._on_error(task)
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error_message = str(exc)
            if self._on_error:
                self._on_error(task)
        finally:
            self._cleanup_temporary_subtitles()

    def _parse_progress(self, process: subprocess.Popen, task: CompressTask,
                        total_duration: float):
        """解析FFmpeg的进度输出"""
        progress_data = {}
        last_update_time = time.time()

        while True:
            if self._cancelled:
                break

            if process.stdout is None:
                break

            line = process.stdout.readline()
            if not line:
                # stdout已关闭（FFmpeg编码完成，进入最终封装阶段）
                # 不再等待process.poll()，直接退出让_run_process处理最终状态
                break

            line = line.strip()

            if "=" in line:
                key, _, value = line.partition("=")
                progress_data[key.strip()] = value.strip()

                # 每帧更新一次进度
                if key.strip() == "out_time_us":
                    try:
                        current_us = int(value.strip())
                        current_sec = current_us / 1_000_000

                        if total_duration > 0:
                            task.progress = min(100.0, (current_sec / total_duration) * 100)

                        # 计算速度
                        elapsed = time.time() - self._start_time
                        task.elapsed_time = elapsed

                        if current_sec > 0 and elapsed > 0:
                            speed = current_sec / elapsed
                            task.speed = f"{speed:.1f}x"

                            # 预估剩余时间
                            if total_duration > 0 and speed > 0:
                                remaining_sec = total_duration - current_sec
                                task.remaining_time = remaining_sec / speed

                        if self._on_progress:
                            self._on_progress(task)

                    except (ValueError, ZeroDivisionError):
                        pass

                elif key.strip() == "speed":
                    task.speed = value.strip()

    def cancel(self):
        """取消当前任务"""
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
                time.sleep(0.5)
                if self._process.poll() is None:
                    self._process.kill()
            except Exception:
                pass

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._thread is not None and self._thread.is_alive()

    @staticmethod
    def generate_output_path(input_file: str, output_dir: str = "",
                             suffix: str = "_720p",
                             reserved_paths: set = None) -> str:
        """生成输出文件路径，并避开本批并行任务已预留的文件名。"""
        dir_name = output_dir or os.path.dirname(input_file)
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_name = f"{base_name}{suffix}.mp4"
        output_path = os.path.join(dir_name, output_name)
        reserved_paths = reserved_paths or set()

        # 避免重名
        counter = 1
        while os.path.exists(output_path) or output_path in reserved_paths:
            output_name = f"{base_name}{suffix}_{counter}.mp4"
            output_path = os.path.join(dir_name, output_name)
            counter += 1

        return output_path
