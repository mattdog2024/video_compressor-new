"""字幕尺寸和极速输出体积的平衡回归测试。"""
import unittest

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine


class SubtitleSizeAndFastVolumeTests(unittest.TestCase):
    def test_user_sample_ass_uses_moderate_single_language_480p_font_size(self):
        engine = FFmpegEngine()
        command = engine.build_command(
            CompressTask(1, "sample.mkv", "output.mp4"),
            CompressOptions(
                resolution="480p", quality="极速", encoder="h264_nvenc",
                subtitle_mode="external", external_subtitle_path="clean.srt",
                subtitle_font_size=24,
            ),
            source_height=690,
        )
        filter_text = command[command.index("-vf") + 1]
        self.assertIn("FontSize=28", filter_text)
        self.assertIn("Outline=2", filter_text)
        self.assertEqual(command[command.index("-b:v") + 1], "400k")
        self.assertEqual(command[command.index("-maxrate") + 1], "480k")

    def test_two_hour_480p_fast_target_is_near_user_size_goal(self):
        duration_seconds = 1 * 3600 + 54 * 60
        video_kbps = 400
        audio_kbps = 96
        estimated_mb = (video_kbps + audio_kbps) * 1000 * duration_seconds / 8 / 1_000_000
        self.assertGreaterEqual(estimated_mb, 420)
        self.assertLessEqual(estimated_mb, 430)


if __name__ == "__main__":
    unittest.main()
