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

    def test_cpu_fast_preset_uses_smallest_fast_parameters(self):
        """CPU极速模式应使用CRF30、ultrafast和96k音频。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(quality="极速", encoder="libx264"),
            total_duration=10,
            source_height=480,
        )

        self.assertEqual(self.option_value(command, "-c:v"), "libx264")
        self.assertEqual(self.option_value(command, "-crf"), "30")
        self.assertEqual(self.option_value(command, "-preset"), "ultrafast")
        self.assertEqual(self.option_value(command, "-b:a"), "96k")
        self.assertNotIn("-tune", command)
        self.assertEqual(self.option_value(command, "-pix_fmt"), "yuv420p")
        self.assertEqual(self.option_value(command, "-ar"), "48000")

    def test_nvenc_fast_preset_prioritizes_speed(self):
        """NVIDIA极速模式应采用最快预设和普通VBR，不走高质量VBR。"""
        command = self.engine.build_command(
            self.task,
            CompressOptions(quality="极速", encoder="h264_nvenc"),
            total_duration=10,
            source_height=480,
        )

        self.assertEqual(self.option_value(command, "-rc"), "vbr")
        self.assertEqual(self.option_value(command, "-preset"), "p1")
        self.assertEqual(self.option_value(command, "-cq"), "30")
        self.assertEqual(self.option_value(command, "-b:a"), "96k")

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
