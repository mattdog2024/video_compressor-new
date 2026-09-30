"""图片字幕保留原片位置的回归测试。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine


class BitmapSubtitleAutoSizeTests(unittest.TestCase):
    def test_legacy_scale_factor_stays_available_for_ui_hint_only(self):
        scale = FFmpegEngine._bitmap_subtitle_scale_factor
        self.assertEqual(scale("480p", 1080), 2.0)
        self.assertAlmostEqual(scale("720p", 1080), 960 / 720, places=2)
        self.assertEqual(scale("1080p", 1080), 1.0)
        # 选择 720p 但源视频只有 480p 时，程序不放大视频，字幕按 480p 输出适配。
        self.assertEqual(scale("720p", 480), 2.0)
        self.assertEqual(scale("原始分辨率", 1080), 1.0)

    def test_command_preserves_bitmap_canvas_coordinates(self):
        command = FFmpegEngine().build_command(
            CompressTask(1, "movie.mkv", "output.mp4"),
            CompressOptions(
                resolution="480p", subtitle_mode="embedded",
                subtitle_stream_index=7, subtitle_stream_ordinal=1,
                subtitle_codec="hdmv_pgs_subtitle",
            ),
            source_height=1080,
        )
        graph = command[command.index("-filter_complex") + 1]
        self.assertNotIn("[subs]scale=", graph)
        self.assertIn("[vbase][subs]overlay=shortest=0:eof_action=pass:repeatlast=1:alpha=straight:format=auto", graph)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_full_canvas_bitmap_layer_keeps_visible_text_inside_480p_frame(self):
        """模拟 PGS 的全透明画布，确认缩小时不把字幕推到画面外。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            work = Path(temp_dir)
            canvas = work / "subtitle_canvas.png"
            baseline = work / "baseline.png"
            safe = work / "safe.png"
            layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer)
            # 纯白矩形模拟图片字幕的实际文字区域，位于原始 1080p 画布底部。
            draw.rectangle((660, 970, 1260, 1010), fill=(255, 255, 255, 255))
            layer.save(canvas)

            commands = {
                baseline: "[0:v][1:v]scale2ref[subs][vbase];[vbase][subs]overlay=0:0[burned];[burned]scale=-2:480[out]",
                safe: "[0:v][1:v]scale2ref[subs][vbase];[vbase][subs]overlay=shortest=0:eof_action=pass:repeatlast=1[burned];[burned]scale=-2:480[out]",
            }
            for output, graph in commands.items():
                subprocess.run([
                    "ffmpeg", "-y", "-loop", "1", "-framerate", "25", "-i", str(canvas),
                    "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=25:d=1",
                    "-filter_complex", graph, "-map", "[out]", "-frames:v", "1", str(output),
                ], check=True, capture_output=True, text=True)

            def visible_box(image_path):
                image = Image.open(image_path).convert("RGB")
                pixels = [
                    (x, y) for y in range(image.height) for x in range(image.width)
                    if min(image.getpixel((x, y))) > 220
                ]
                xs, ys = zip(*pixels)
                return min(xs), min(ys), max(xs), max(ys)

            self.assertEqual(visible_box(safe), visible_box(baseline))
            _, top, _, bottom = visible_box(safe)
            self.assertGreater(top, 400)
            self.assertLess(bottom, 480)


if __name__ == "__main__":
    unittest.main()
