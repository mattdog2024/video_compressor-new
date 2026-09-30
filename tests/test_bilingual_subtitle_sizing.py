"""中英双语字幕自动识别和字号控制回归测试。"""
import tempfile
import unittest
from pathlib import Path

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine
from core.subtitle import has_bilingual_subtitles


class BilingualSubtitleSizingTests(unittest.TestCase):
    def setUp(self):
        self.engine = FFmpegEngine()
        self.task = CompressTask(1, "input.mkv", "output.mp4")

    def _write_subtitle(self, content: str) -> str:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "subtitle.srt"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_bilingual_detector_requires_cjk_and_latin_letters(self):
        chinese_only = self._write_subtitle(
            "1\n00:00:00,000 --> 00:00:02,000\n他说得很清楚。\n"
        )
        bilingual = self._write_subtitle(
            "1\n00:00:00,000 --> 00:00:02,000\n他说得很清楚。\nHe made it very clear.\n"
        )
        self.assertFalse(has_bilingual_subtitles(chinese_only))
        self.assertTrue(has_bilingual_subtitles(bilingual))

    def test_480p_bilingual_uses_26_and_single_language_uses_28(self):
        chinese_only = self._write_subtitle(
            "1\n00:00:00,000 --> 00:00:02,000\n他说得很清楚。\n"
        )
        bilingual = self._write_subtitle(
            "1\n00:00:00,000 --> 00:00:02,000\n他说得很清楚。\nHe made it very clear.\n"
        )
        base = dict(
            resolution="480p", quality="极速", encoder="h264_nvenc",
            subtitle_mode="external", subtitle_font_size=24,
        )
        single_command = self.engine.build_command(
            self.task, CompressOptions(**base, external_subtitle_path=chinese_only),
            source_height=690,
        )
        bilingual_command = self.engine.build_command(
            self.task, CompressOptions(**base, external_subtitle_path=bilingual),
            source_height=690,
        )
        single_filter = single_command[single_command.index("-vf") + 1]
        bilingual_filter = bilingual_command[bilingual_command.index("-vf") + 1]
        self.assertIn("FontSize=28", single_filter)
        self.assertIn("FontSize=26", bilingual_filter)
        self.assertIn("Outline=2", single_filter)
        self.assertIn("Outline=2", bilingual_filter)

    def test_manual_larger_font_size_is_preserved_for_bilingual(self):
        bilingual = self._write_subtitle(
            "1\n00:00:00,000 --> 00:00:02,000\n中文\nEnglish\n"
        )
        command = self.engine.build_command(
            self.task,
            CompressOptions(
                resolution="480p", subtitle_mode="external",
                external_subtitle_path=bilingual, subtitle_font_size=32,
            ),
            source_height=690,
        )
        filter_text = command[command.index("-vf") + 1]
        self.assertIn("FontSize=32", filter_text)


if __name__ == "__main__":
    unittest.main()
