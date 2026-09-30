"""每个排队视频独立选择内置字幕的回归测试。"""
import unittest
from pathlib import Path

from core.probe import SubtitleStream
from core.subtitle import select_embedded_subtitle_stream


class PerFileSubtitleSelectionTests(unittest.TestCase):
    def setUp(self):
        self.first_video_streams = [
            SubtitleStream(2, 0, "subrip", "chi", "中文", True),
            SubtitleStream(3, 1, "subrip", "eng", "English", False),
        ]
        self.second_video_streams = [
            SubtitleStream(7, 0, "ass", "eng", "English", True),
            SubtitleStream(8, 1, "ass", "chi", "中文", False),
        ]

    def test_three_file_selections_do_not_override_each_other(self):
        selections = {1: 3, 2: 8, 3: None}
        third_video_streams = [
            SubtitleStream(11, 0, "subrip", "jpn", "日本語", False),
            SubtitleStream(12, 1, "subrip", "chi", "中文", True),
        ]
        selected_one = select_embedded_subtitle_stream(
            self.first_video_streams, selections[1]
        )
        selected_two = select_embedded_subtitle_stream(
            self.second_video_streams, selections[2]
        )
        selected_three = select_embedded_subtitle_stream(
            third_video_streams, selections[3]
        )
        self.assertEqual(selected_one.index, 3)
        self.assertEqual(selected_two.index, 8)
        self.assertEqual(selected_three.index, 12)

    def test_invalid_selection_only_falls_back_inside_its_own_file(self):
        selected = select_embedded_subtitle_stream(self.first_video_streams, 8)
        self.assertEqual(selected.index, 2)
        self.assertNotIn(selected.index, {stream.index for stream in self.second_video_streams})

    def test_gui_contains_per_file_selection_map_and_scroll_panel(self):
        source = (Path(__file__).resolve().parents[1] / "gui" / "app.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self._embedded_subtitle_selections", source)
        self.assertIn("def _create_subtitle_selection_row", source)
        self.assertIn("def _on_file_subtitle_stream_selected", source)
        self.assertIn("subtitle_selection_canvas", source)
        self.assertNotIn("self.subtitle_stream_combo", source)


if __name__ == "__main__":
    unittest.main()
