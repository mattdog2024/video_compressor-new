"""图片字幕按输出分辨率自动放大的回归测试。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine


class BitmapSubtitleAutoSizeTests(unittest.TestCase):
    def test_scale_factor_tracks_effective_output_height(self):
        scale = FFmpegEngine._bitmap_subtitle_scale_factor
        self.assertEqual(scale("480p", 1080), 2.0)
        self.assertAlmostEqual(scale("720p", 1080), 960 / 720, places=2)
        self.assertEqual(scale("1080p", 1080), 1.0)
        # 选择 720p 但源视频只有 480p 时，程序不放大视频，字幕按 480p 输出适配。
        self.assertEqual(scale("720p", 480), 2.0)
        self.assertEqual(scale("原始分辨率", 1080), 1.0)

    def test_command_enlarges_480p_bitmap_subtitles_and_anchors_bottom(self):
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
        self.assertIn("[subs]scale=trunc(iw*2.00/2)*2", graph)
        self.assertIn("overlay=x=(W-w)/2:y=H-h", graph)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_full_canvas_bitmap_layer_visibly_grows_at_480p(self):
        """模拟 PGS 的全透明画布，确认 480p 输出时可见字幕面积至少变大一倍。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            work = Path(temp_dir)
            canvas = work / "subtitle_canvas.png"
            baseline = work / "baseline.png"
            enhanced = work / "enhanced.png"
            layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer)
            # 纯白矩形模拟图片字幕的实际文字区域，位于原始 1080p 画布底部。
            draw.rectangle((660, 970, 1260, 1010), fill=(255, 255, 255, 255))
            layer.save(canvas)

            commands = {
                baseline: (
                    "[0:v][1:v]scale2ref[subs][vbase];"
                    "[vbase][subs]overlay=0:0[burned];[burned]scale=-2:480[out]"
                ),
                enhanced: (
                    "[0:v][1:v]scale2ref[subs][vbase];"
                    "[subs]scale=trunc(iw*2/2)*2:trunc(ih*2/2)*2:flags=lanczos[autosubs];"
                    "[vbase][autosubs]overlay=x=(W-w)/2:y=H-h[burned];"
                    "[burned]scale=-2:480[out]"
                ),
            }
            for output, graph in commands.items():
                subprocess.run([
                    "ffmpeg", "-y", "-loop", "1", "-framerate", "25", "-i", str(canvas),
                    "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=25:d=1",
                    "-filter_complex", graph, "-map", "[out]", "-frames:v", "1", str(output),
                ], check=True, capture_output=True, text=True)

            def visible_area(image_path):
                image = Image.open(image_path).convert("RGB")
                pixels = [
                    (x, y) for y in range(image.height) for x in range(image.width)
                    if min(image.getpixel((x, y))) > 220
                ]
                xs, ys = zip(*pixels)
                return (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)

            self.assertGreater(visible_area(enhanced), visible_area(baseline) * 3)


if __name__ == "__main__":
    unittest.main()
