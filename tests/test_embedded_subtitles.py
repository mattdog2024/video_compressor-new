"""内置字幕烧录的命令和真实转码回归测试。"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine
from core.probe import _parse_probe_data, probe_video


class EmbeddedSubtitleCommandTests(unittest.TestCase):
    def setUp(self):
        self.engine = FFmpegEngine()
        self.task = CompressTask(1, "movie.mkv", "output.mp4")

    @staticmethod
    def option_value(command, option):
        return command[command.index(option) + 1]

    def test_probe_records_global_index_and_subtitle_ordinal(self):
        """字幕流的容器索引与字幕序号必须分开保存。"""
        data = {
            "format": {"duration": "10", "format_name": "matroska"},
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 640,
                 "height": 360, "r_frame_rate": "25/1"},
                {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2},
                {"index": 4, "codec_type": "subtitle", "codec_name": "ass",
                 "disposition": {"default": 1}, "tags": {"language": "chi"}},
                {"index": 7, "codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle",
                 "width": 1280, "height": 720,
                 "disposition": {"default": 0}, "tags": {"language": "eng"}},
            ],
        }
        info = _parse_probe_data(data, "movie.mkv", "movie.mkv", 1)
        self.assertEqual([(item.index, item.ordinal) for item in info.subtitle_streams], [(4, 0), (7, 1)])
        self.assertEqual((info.subtitle_streams[1].width, info.subtitle_streams[1].height), (1280, 720))

    def test_text_embedded_subtitle_burns_directly_from_container(self):
        """文本内置字幕应直接从视频容器读取，而非先提取为临时 SRT。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(
                encoder="libx264", subtitle_mode="embedded",
                subtitle_stream_index=4, subtitle_stream_ordinal=1, subtitle_codec="ass",
            ),
            total_duration=10,
            source_height=480,
        )
        filter_text = self.option_value(command, "-vf")
        self.assertIn("subtitles=filename='movie.mkv':si=1", filter_text)
        self.assertEqual(self.option_value(command, "-map"), "0:v:0")
        self.assertIn("0:a:0?", command)
        self.assertNotIn("-filter_complex", command)

    def test_bitmap_embedded_subtitle_uses_overlay(self):
        """PGS 等图片字幕必须走图层叠加，不允许按文本字幕处理。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(
                encoder="libx264", subtitle_mode="embedded",
                subtitle_stream_index=7, subtitle_stream_ordinal=1,
                subtitle_codec="hdmv_pgs_subtitle", subtitle_canvas_width=1280,
                subtitle_canvas_height=720,
            ),
            total_duration=10,
            source_height=480,
        )
        filter_complex = self.option_value(command, "-filter_complex")
        self.assertEqual(self.option_value(command, "-canvas_size"), "1280x720")
        self.assertIn("-fix_sub_duration", command)
        self.assertIn("[0:s:1]", filter_complex)
        self.assertIn("scale2ref[subs][vbase]", filter_complex)
        self.assertNotIn("[subs]scale=", filter_complex)
        self.assertIn("[vbase][subs]overlay=shortest=0:eof_action=pass:repeatlast=1:alpha=straight:format=auto", filter_complex)
        self.assertIn("[burned]scale=", filter_complex)
        map_positions = [index for index, value in enumerate(command) if value == "-map"]
        self.assertEqual(command[map_positions[0] + 1], "[vout]")
        self.assertEqual(command[map_positions[1] + 1], "0:a:0?")

    def test_bitmap_subtitle_uses_handbrake_native_burn_command(self):
        """PGS 图片字幕应由 HandBrake 原生烧录器处理，避免 FFmpeg 空图层。"""
        options = CompressOptions(
            resolution="480p", quality="极速", encoder="h264_nvenc",
            subtitle_mode="embedded", subtitle_stream_index=7,
            subtitle_stream_ordinal=1, subtitle_codec="hdmv_pgs_subtitle", volume=60,
        )
        command = self.engine.build_handbrake_command(
            self.task, options, total_duration=120, source_height=692,
        )
        self.assertIn("--subtitle", command)
        self.assertEqual(self.option_value(command, "--subtitle"), "2")
        self.assertIn("--subtitle-burned=1", command)
        self.assertEqual(self.option_value(command, "--encoder"), "nvenc_h264")
        self.assertEqual(self.option_value(command, "--vb"), "900")
        self.assertEqual(self.option_value(command, "--ab"), "128")
        self.assertEqual(self.option_value(command, "--gain"), "-4.44")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe not installed")
class EmbeddedSubtitleIntegrationTests(unittest.TestCase):
    def test_text_subtitle_is_visibly_burned_and_not_copied_as_stream(self):
        """真实 MKV 内置 SRT 烧录后，MP4 必须有画面字幕且不再保留字幕流。"""
        engine = FFmpegEngine()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            subtitle = temp_path / "track.srt"
            source = temp_path / "source_with_subtitle.mkv"
            output = temp_path / "burned.mp4"
            frame = temp_path / "frame.png"
            subtitle.write_text(
                "1\n00:00:00,100 --> 00:00:00,900\nBURN TEST\n",
                encoding="utf-8",
            )
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=1",
                "-i", str(subtitle),
                "-map", "0:v:0", "-map", "1:s:0",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:s", "srt",
                "-shortest", str(source),
            ], check=True, capture_output=True, text=True)

            info = probe_video(str(source))
            self.assertIsNotNone(info)
            selected_subtitle = info.subtitle_streams[0]
            command = engine.build_command(
                CompressTask(1, str(source), str(output)),
                CompressOptions(
                    encoder="libx264", resolution="原始分辨率", quality="极速",
                    subtitle_mode="embedded", subtitle_stream_index=selected_subtitle.index,
                    subtitle_stream_ordinal=selected_subtitle.ordinal,
                    subtitle_codec=selected_subtitle.codec,
                ),
                total_duration=info.duration,
                source_height=info.video_height,
            )
            subprocess.run(command, check=True, capture_output=True, text=True)

            metadata = json.loads(subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)],
                check=True, capture_output=True, text=True,
            ).stdout)
            self.assertFalse(any(item["codec_type"] == "subtitle" for item in metadata["streams"]))

            subprocess.run([
                "ffmpeg", "-y", "-ss", "0.5", "-i", str(output), "-frames:v", "1", str(frame),
            ], check=True, capture_output=True, text=True)
            image = Image.open(frame).convert("L")
            self.assertGreater(max(image.get_flattened_data()), 40)


if __name__ == "__main__":
    unittest.main()
