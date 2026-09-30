"""HandBrake 原生图片字幕烧录的真实回归测试。"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine
from utils.helpers import get_handbrake_path, handbrake_available


@unittest.skipUnless(handbrake_available() and shutil.which("ffmpeg"), "HandBrakeCLI/FFmpeg not installed")
class HandBrakeBitmapSubtitleTests(unittest.TestCase):
    def test_pgs_track_is_actually_burned_into_video_pixels(self):
        """公开 PGS 样本即使 FFmpeg 报调色板警告，也必须烧出画面差异。"""
        fixture = Path("/tmp/pgs-repro/extracted/Mob Psycho 100 S01 E06-1.mkv")
        if not fixture.exists():
            self.skipTest("public PGS fixture not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            work = Path(temp_dir)
            source = work / "source.mp4"
            burned = work / "burned.mp4"
            base = [
                get_handbrake_path(), "-i", str(fixture), "--format", "av_mp4",
                "--encoder", "x264", "--quality", "18", "--encoder-preset", "veryfast",
                "--audio", "none", "--start-at", "duration:0", "--stop-at", "duration:20",
                "--width", "0", "--height", "480",
            ]
            subprocess.run(base + ["-o", str(source)], check=True, capture_output=True, text=True)
            subprocess.run(
                base + ["-o", str(burned), "--subtitle", "1", "--subtitle-burned=1"],
                check=True, capture_output=True, text=True,
            )

            def frame_at(video_path, second):
                return subprocess.check_output([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(second),
                    "-i", str(video_path), "-frames:v", "1", "-f", "rawvideo",
                    "-pix_fmt", "rgb24", "-",
                ])

            # 样本前 20 秒包含图片字幕。只要任一点有大面积画面差异，即证明字幕
            # 已烧进画面，而不是仅复制了一个不可播放的字幕流。
            differences = []
            for second in range(20):
                original = frame_at(source, second)
                rendered = frame_at(burned, second)
                changed = sum(left != right for left, right in zip(original, rendered))
                if changed > 1000:
                    differences.append(changed)
            self.assertTrue(differences, "HandBrake output did not contain burned PGS pixels")

    def test_engine_routes_bitmap_subtitles_to_handbrake(self):
        engine = FFmpegEngine()
        options = CompressOptions(
            subtitle_mode="embedded", subtitle_stream_ordinal=0,
            subtitle_codec="dvd_subtitle", encoder="libx264",
        )
        self.assertTrue(engine._uses_bitmap_subtitle_backend(options))
        command = engine.build_handbrake_command(
            CompressTask(1, "input.mkv", "output.mp4"), options, source_height=480,
        )
        self.assertIn("--subtitle-burned=1", command)
        self.assertEqual(command[command.index("--encoder") + 1], "x264")


if __name__ == "__main__":
    unittest.main()
