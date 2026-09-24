"""平台兼容 MP4 输出的回归测试。"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine
from utils.helpers import get_ffmpeg_path, get_ffprobe_path


class PlatformCompatibilityCommandTests(unittest.TestCase):
    def setUp(self):
        self.engine = FFmpegEngine()
        self.task = CompressTask(1, "input.mp4", "output.mp4")

    def test_default_command_forces_8_bit_platform_mp4(self):
        """默认输出必须明确要求H.264 Main、8位YUV420P、AAC-LC 48k。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(encoder="libx264"),
            total_duration=10,
            source_height=480,
        )

        self.assertEqual(command[command.index("-profile:v") + 1], "main")
        self.assertEqual(command[command.index("-pix_fmt") + 1], "yuv420p")
        self.assertEqual(command[command.index("-profile:a") + 1], "aac_low")
        self.assertEqual(command[command.index("-ar") + 1], "48000")
        self.assertIn("+faststart", command)

    def test_compatibility_mode_converts_h265_selection_to_h264(self):
        """平台兼容模式不允许HEVC作为最终输出。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(encoder="libx265"),
            total_duration=10,
            source_height=480,
        )
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")

    def test_compatibility_can_be_explicitly_disabled(self):
        """仅在用户主动关闭时，才保留原始编码选择。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(encoder="libx265", platform_compatibility=False),
            total_duration=10,
            source_height=480,
        )
        self.assertEqual(command[command.index("-c:v") + 1], "libx265")
        self.assertNotIn("-pix_fmt", command)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe not installed")
class PlatformCompatibilityIntegrationTests(unittest.TestCase):
    def test_10_bit_input_becomes_platform_compatible_mp4(self):
        """真实转码：10位 High 10 输入必须落为8位 Main + AAC-LC 48k。"""
        engine = FFmpegEngine()
        ffmpeg = get_ffmpeg_path()
        ffprobe = get_ffprobe_path()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source_high10.mp4"
            output = temp_path / "output_platform.mp4"

            create_source = [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", "testsrc2=size=854x480:rate=25:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100:duration=1",
                "-filter:v", "format=yuv420p10le",
                "-c:v", "libx264", "-profile:v", "high10", "-pix_fmt", "yuv420p10le",
                "-c:a", "aac", "-ar", "44100", "-shortest", str(source),
            ]
            subprocess.run(create_source, check=True, capture_output=True, text=True)

            task = CompressTask(1, str(source), str(output))
            command = engine.build_command(
                task,
                CompressOptions(encoder="libx264", resolution="480p"),
                total_duration=1,
                source_height=480,
            )
            subprocess.run(command, check=True, capture_output=True, text=True)

            probe = subprocess.run(
                [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)],
                check=True, capture_output=True, text=True,
            )
            metadata = json.loads(probe.stdout)
            video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
            audio = next(stream for stream in metadata["streams"] if stream["codec_type"] == "audio")

            self.assertEqual(video["codec_name"], "h264")
            self.assertEqual(video["profile"], "Main")
            self.assertEqual(video["pix_fmt"], "yuv420p")
            self.assertEqual(audio["codec_name"], "aac")
            self.assertEqual(audio["profile"], "LC")
            self.assertEqual(audio["sample_rate"], "48000")

            # faststart：moov元数据在mdat视频数据前，适合上传后边下边播。
            file_bytes = output.read_bytes()
            self.assertLess(file_bytes.find(b"moov"), file_bytes.find(b"mdat"))


if __name__ == "__main__":
    unittest.main()
