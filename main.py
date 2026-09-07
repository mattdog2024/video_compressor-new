"""万能视频压缩器 - 主入口"""
import sys
import os
import logging

# 设置路径
if getattr(sys, 'frozen', False):
    # PyInstaller打包后
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, '_MEIPASS', BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

# 确保项目根目录在sys.path中
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if BUNDLE_DIR not in sys.path:
    sys.path.insert(0, BUNDLE_DIR)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)

# 如果打包后，也写到文件
if getattr(sys, 'frozen', False):
    log_file = os.path.join(BASE_DIR, "compressor.log")
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logging.getLogger().addHandler(file_handler)
    except Exception:
        pass

logger = logging.getLogger(__name__)


def check_ffmpeg():
    """检查FFmpeg是否可用"""
    from utils.helpers import get_ffmpeg_path, get_ffprobe_path
    import subprocess

    ffmpeg = get_ffmpeg_path()
    ffprobe = get_ffprobe_path()

    # 测试ffmpeg
    try:
        result = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            logger.info(f"FFmpeg可用: {ffmpeg}")
            return True
    except Exception as e:
        logger.warning(f"FFmpeg不可用: {e}")

    return False


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("万能视频压缩器 v1.0 启动")
    logger.info("=" * 50)

    # 检查FFmpeg
    if not check_ffmpeg():
        logger.warning("FFmpeg未找到！部分功能将不可用。")
        logger.warning("请将ffmpeg.exe和ffprobe.exe放在程序目录下的ffmpeg文件夹中")

    # 启动GUI
    from gui.app import VideoCompressorApp
    app = VideoCompressorApp()
    app.run()


if __name__ == "__main__":
    main()
