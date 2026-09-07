"""硬件检测模块 - 自动检测CPU/GPU编码能力"""
import subprocess
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from utils.helpers import get_ffmpeg_path

logger = logging.getLogger(__name__)


@dataclass
class EncoderInfo:
    """编码器信息"""
    name: str           # 编码器名称 (h264_nvenc, h264_qsv, etc.)
    display_name: str   # 显示名称
    type: str           # "gpu" 或 "cpu"
    gpu_brand: str      # "NVIDIA", "Intel", "AMD", ""
    available: bool = False


@dataclass
class HardwareProfile:
    """硬件配置"""
    cpu_encoders: List[EncoderInfo] = field(default_factory=list)
    gpu_encoders: List[EncoderInfo] = field(default_factory=list)
    best_gpu: Optional[EncoderInfo] = None
    best_cpu: Optional[EncoderInfo] = None
    ffmpeg_version: str = ""
    detection_log: str = ""


def detect_hardware() -> HardwareProfile:
    """检测系统硬件编码能力"""
    profile = HardwareProfile()
    log_lines = []

    # 获取FFmpeg版本
    try:
        result = subprocess.run(
            [get_ffmpeg_path(), "-version"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if _is_windows() else 0
        )
        output = result.stdout + result.stderr
        version_match = re.search(r"ffmpeg version\s+(\S+)", output)
        if version_match:
            profile.ffmpeg_version = version_match.group(1)
            log_lines.append(f"FFmpeg版本: {profile.ffmpeg_version}")
    except Exception as e:
        log_lines.append(f"获取FFmpeg版本失败: {e}")

    # 获取所有可用编码器
    try:
        result = subprocess.run(
            [get_ffmpeg_path(), "-encoders", "-hide_banner"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if _is_windows() else 0
        )
        encoder_output = result.stdout
        log_lines.append("成功获取编码器列表")
    except Exception as e:
        log_lines.append(f"获取编码器列表失败: {e}")
        encoder_output = ""

    # 要检测的编码器
    encoders_to_check = [
        EncoderInfo("h264_nvenc", "NVIDIA NVENC (H.264)", "gpu", "NVIDIA"),
        EncoderInfo("hevc_nvenc", "NVIDIA NVENC (H.265)", "gpu", "NVIDIA"),
        EncoderInfo("h264_qsv", "Intel QuickSync (H.264)", "gpu", "Intel"),
        EncoderInfo("hevc_qsv", "Intel QuickSync (H.265)", "gpu", "Intel"),
        EncoderInfo("h264_amf", "AMD AMF (H.264)", "gpu", "AMD"),
        EncoderInfo("hevc_amf", "AMD AMF (H.265)", "gpu", "AMD"),
        EncoderInfo("libx264", "CPU x264 (H.264)", "cpu", ""),
        EncoderInfo("libx265", "CPU x265 (H.265)", "cpu", ""),
    ]

    for enc in encoders_to_check:
        # 在编码器列表中查找
        pattern = rf"\b{re.escape(enc.name)}\b"
        if re.search(pattern, encoder_output):
            enc.available = True
            if enc.type == "gpu":
                profile.gpu_encoders.append(enc)
                log_lines.append(f"✓ 检测到GPU编码器: {enc.display_name}")
            else:
                profile.cpu_encoders.append(enc)
                log_lines.append(f"✓ 检测到CPU编码器: {enc.display_name}")
        else:
            log_lines.append(f"✗ 未检测到: {enc.display_name}")

    # 确定最佳GPU编码器（优先级: NVENC > QSV > AMF）
    gpu_priority = ["NVIDIA", "Intel", "AMD"]
    for brand in gpu_priority:
        for enc in profile.gpu_encoders:
            if enc.gpu_brand == brand and "h264" in enc.name:
                profile.best_gpu = enc
                break
        if profile.best_gpu:
            break

    # 确定最佳CPU编码器
    for enc in profile.cpu_encoders:
        if enc.name == "libx264":
            profile.best_cpu = enc
            break
    if not profile.best_cpu and profile.cpu_encoders:
        profile.best_cpu = profile.cpu_encoders[0]

    profile.detection_log = "\n".join(log_lines)
    logger.info(f"硬件检测完成: GPU={profile.best_gpu}, CPU={profile.best_cpu}")
    return profile


def get_encoder_choices(profile: HardwareProfile) -> list:
    """获取可用的编码器选项列表，用于GUI下拉框"""
    choices = []

    # 自动选项
    if profile.best_gpu:
        choices.append(("自动 (GPU加速)", "auto"))
    else:
        choices.append(("自动 (CPU)", "auto"))

    # GPU编码器
    for enc in profile.gpu_encoders:
        if enc.available:
            choices.append((f"GPU - {enc.display_name}", enc.name))

    # CPU编码器
    for enc in profile.cpu_encoders:
        if enc.available:
            choices.append((f"CPU - {enc.display_name}", enc.name))

    return choices


def _is_windows():
    """检测是否为Windows系统"""
    import sys
    return sys.platform == "win32"
