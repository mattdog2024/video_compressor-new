"""极速模式的速度与体积参数回归测试。"""
import unittest

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine


class FastPresetTests(unittest.TestCase):
    def setUp(self):
        self.engine = FFmpegEngine()
        self.task = CompressTask(1, "input.mp4", "output.mp4")

    @staticmethod
    def option_value(command, option):
        return command[command.index(option) + 1]

    def test_cpu_fast_preset_keeps_reasonable_quality(self):
        """CPU极速模式应保持速度，同时不使用过度压缩的 CRF30/96k。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(quality="极速", encoder="libx264"),
            total_duration=10,
            source_height=480,
        )

        self.assertEqual(self.option_value(command, "-c:v"), "libx264")
        self.assertEqual(self.option_value(command, "-crf"), "26")
        self.assertEqual(self.option_value(command, "-preset"), "ultrafast")
        self.assertEqual(self.option_value(command, "-b:a"), "128k")
        self.assertNotIn("-tune", command)
        self.assertEqual(self.option_value(command, "-pix_fmt"), "yuv420p")
        self.assertEqual(self.option_value(command, "-ar"), "48000")

    def test_nvenc_fast_preset_keeps_quality_floor(self):
        """NVIDIA极速模式应快速且有码率底线，避免长片糊成马赛克。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(quality="极速", encoder="h264_nvenc"),
            total_duration=10,
            source_height=480,
        )

        self.assertEqual(self.option_value(command, "-rc"), "vbr")
        self.assertEqual(self.option_value(command, "-preset"), "p2")
        self.assertEqual(self.option_value(command, "-cq"), "26")
        self.assertEqual(self.option_value(command, "-b:v"), "900k")
        self.assertEqual(self.option_value(command, "-maxrate"), "1200k")
        self.assertEqual(self.option_value(command, "-bufsize"), "1800k")
        self.assertEqual(self.option_value(command, "-b:a"), "128k")

    def test_nvenc_fast_rate_scales_with_output_height(self):
        rate = self.engine._fast_nvenc_target_rate
        self.assertEqual(rate("480p", 690), "900k")
        self.assertEqual(rate("720p", 1080), "1400k")
        self.assertEqual(rate("1080p", 1080), "3000k")

    def test_standard_preset_keeps_selected_audio_bitrate(self):
        """非极速模式不应无声覆盖用户选择的音频码率。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(quality="标准", encoder="libx264", audio_bitrate="192k"),
            total_duration=10,
            source_height=480,
        )
        self.assertEqual(self.option_value(command, "-b:a"), "192k")


if __name__ == "__main__":
    unittest.main()
