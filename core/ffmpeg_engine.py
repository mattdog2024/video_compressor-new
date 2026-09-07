"""FFmpeg引擎 - 构建命令、执行压缩、解析进度"""
import os
import re
import subprocess
import threading
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, List
from enum import Enum

from utils.helpers import (
    get_ffmpeg_path, RESOLUTION_MAP, QUALITY_PRESETS
)
from core.subtitle import (
    extract_subtitle, build_subtitle_filter, get_subtitle_filter_for_external
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
    external_subtitle_path: str = ""
    subtitle_font_size: int = 24
    subtitle_font_color: str = "#FFFFFF"
    gpu_encoder: str = ""        # 具体GPU编码器名
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

    def build_command(self, task: CompressTask, options: CompressOptions,
                      total_duration: float = 0,
                      source_height: int = 0) -> list:
        """构建FFmpeg命令"""
        cmd = [get_ffmpeg_path()]

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
        if options.subtitle_mode == "embedded" and options.subtitle_stream_index >= 0:
            # 提取内置字幕
            sub_file = extract_subtitle(task.input_file, options.subtitle_stream_index)
            if sub_file:
                vf_parts.append(build_subtitle_filter(
                    sub_file, options.subtitle_font_size, options.subtitle_font_color
                ))
        elif options.subtitle_mode == "external" and options.external_subtitle_path:
            sub_filter = get_subtitle_filter_for_external(
                options.external_subtitle_path,
                options.subtitle_font_size,
                options.subtitle_font_color
            )
            vf_parts.append(sub_filter)

        # === 视频编码 ===
        encoder_name = self._resolve_encoder(options)

        if vf_parts:
            cmd.extend(["-vf", ",".join(vf_parts)])

        # 编码器参数
        quality_config = QUALITY_PRESETS.get(options.quality, QUALITY_PRESETS["标准"])

        if encoder_name in ("h264_nvenc", "hevc_nvenc"):
            # NVIDIA NVENC
            crf = quality_config["crf"]
            cq_value = max(0, min(51, crf))
            cmd.extend(["-c:v", encoder_name])
            cmd.extend(["-rc", "vbr_hq"])
            cmd.extend(["-cq", str(cq_value)])
            cmd.extend(["-preset", "p4"])  # medium quality/speed
            cmd.extend(["-b:v", "0"])
        elif encoder_name in ("h264_qsv", "hevc_qsv"):
            # Intel QuickSync
            crf = quality_config["crf"]
            cmd.extend(["-c:v", encoder_name])
            cmd.extend(["-global_quality", str(crf)])
            cmd.extend(["-preset", quality_config["preset"]])
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
            cmd.extend(["-tune", "film"])

        # === 音频 ===
        if options.remove_audio:
            cmd.extend(["-an"])
        else:
            cmd.extend(["-c:a", "aac"])
            audio_br = options.audio_bitrate
            cmd.extend(["-b:a", audio_br])
            cmd.extend(["-ac", "2"])  # 立体声

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

    def _resolve_encoder(self, options: CompressOptions) -> str:
        """解析编码器选择"""
        if options.encoder == "auto":
            if options.gpu_encoder:
                return options.gpu_encoder
            return "libx264"
        return options.encoder

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

        cmd = self.build_command(task, options, total_duration, source_height=source_height)
        logger.info(f"FFmpeg命令: {' '.join(cmd)}")

        task.status = TaskStatus.RUNNING

        self._thread = threading.Thread(
            target=self._run_process,
            args=(cmd, task, total_duration),
            daemon=True
        )
        self._thread.start()

    def _run_process(self, cmd: list, task: CompressTask, total_duration: float):
        """在后台线程中运行FFmpeg进程"""
        stderr_output = []

        def _drain_stderr():
            """后台读取stderr，防止管道缓冲区填满导致FFmpeg阻塞"""
            try:
                if self._process.stderr:
                    for line in self._process.stderr:
                        stderr_output.append(line)
            except Exception:
                pass

        try:
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

            # 启动stderr后台读取线程，防止缓冲区满导致FFmpeg阻塞
            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            # 解析进度
            self._parse_progress(self._process, task, total_duration)

            # 等待完成
            self._process.wait()

            if self._cancelled:
                task.status = TaskStatus.CANCELLED
            elif self._process.returncode == 0:
                task.status = TaskStatus.COMPLETED
                task.progress = 100.0
                # 获取输出文件大小
                if os.path.exists(task.output_file):
                    task.output_size = os.path.getsize(task.output_file)
                if self._on_complete:
                    self._on_complete(task)
            else:
                err_msg = "".join(stderr_output[-20:]) if stderr_output else "未知错误"
                task.status = TaskStatus.FAILED
                task.error_message = err_msg[-500:]
                if self._on_error:
                    self._on_error(task)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            if self._on_error:
                self._on_error(task)

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
                             suffix: str = "_720p") -> str:
        """生成输出文件路径"""
        dir_name = output_dir or os.path.dirname(input_file)
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_name = f"{base_name}{suffix}.mp4"
        output_path = os.path.join(dir_name, output_name)

        # 避免重名
        counter = 1
        while os.path.exists(output_path):
            output_name = f"{base_name}{suffix}_{counter}.mp4"
            output_path = os.path.join(dir_name, output_name)
            counter += 1

        return output_path
