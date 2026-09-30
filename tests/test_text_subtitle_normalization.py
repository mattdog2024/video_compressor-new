"""文字内置字幕标准化与清晰样式的回归测试。"""
import unittest

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine
from core.subtitle import clean_text_subtitle_content, build_subtitle_filter


class TextSubtitleNormalizationTests(unittest.TestCase):
    def test_complex_ass_and_html_style_is_removed(self):
        styled = (
            "1\n00:00:00,000 --> 00:00:02,000\n"
            "<font size=\"76\"><b>{\\an8\\bord14\\blur4}中文测试\\N"
            "{\\an2}It's about deceiving him, too.</b></font>\n"
        )
        clean = clean_text_subtitle_content(styled)
        self.assertIn("中文测试\nIt's about deceiving him, too.", clean)
        self.assertNotIn("<font", clean)
        self.assertNotIn("\\bord", clean)
        self.assertNotIn("\\blur", clean)
        self.assertNotIn("\\an", clean)

    def test_normalized_subtitle_has_readable_unified_style(self):
        filter_text = build_subtitle_filter("clean.srt", font_size=24)
        self.assertIn("FontName=Microsoft YaHei", filter_text)
        self.assertIn("FontSize=24", filter_text)
        self.assertIn("PrimaryColour=&H00FFFFFF", filter_text)
        self.assertIn("OutlineColour=&H00000000", filter_text)
        self.assertIn("Outline=1.5", filter_text)
        self.assertIn("Shadow=0", filter_text)
        self.assertIn("Alignment=2", filter_text)

    def test_text_subtitle_font_has_output_based_readable_minimum(self):
        auto_size = FFmpegEngine._effective_text_subtitle_font_size
        self.assertEqual(auto_size(24, "480p", 1080), 28)
        self.assertEqual(auto_size(24, "720p", 1080), 36)
        self.assertEqual(auto_size(24, "1080p", 1080), 48)
        self.assertEqual(auto_size(60, "480p", 1080), 60)

    def test_command_uses_auto_text_font_size_for_small_output(self):
        command = FFmpegEngine().build_command(
            CompressTask(1, "movie.mkv", "output.mp4"),
            CompressOptions(
                resolution="480p", subtitle_mode="external",
                external_subtitle_path="track.srt", subtitle_font_size=24,
            ),
            source_height=1080,
        )
        filter_text = command[command.index("-vf") + 1]
        self.assertIn("FontSize=28", filter_text)

    def test_embedded_text_is_replaced_by_clean_external_srt_when_ready(self):
        engine = FFmpegEngine()
        task = CompressTask(1, "input.mkv", "output.mp4")
        options = CompressOptions(
            subtitle_mode="embedded", subtitle_stream_index=2,
            subtitle_stream_ordinal=0, subtitle_codec="subrip",
        )
        original = "core.ffmpeg_engine.prepare_clean_embedded_text_subtitle"
        from unittest.mock import patch
        with patch(original, return_value="/tmp/clean.srt"):
            with patch("core.ffmpeg_engine.tempfile.mkdtemp", return_value="/tmp/subtitle-work"):
                prepared = engine._prepare_text_subtitle_options(task, options)
        self.assertEqual(prepared.subtitle_mode, "external")
        self.assertEqual(prepared.external_subtitle_path, "/tmp/clean.srt")
        self.assertEqual(prepared.subtitle_font_size, 24)


if __name__ == "__main__":
    unittest.main()
