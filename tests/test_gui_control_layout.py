"""确保字幕详情增高时，开始压缩按钮仍在进度区域上方。"""
import unittest
from pathlib import Path


class GuiControlLayoutTests(unittest.TestCase):
    def test_controls_are_packed_before_progress_section(self):
        source = Path(__file__).resolve().parents[1] / "gui" / "app.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn('self.root.geometry("820x980")', text)
        self.assertIn('before=progress_section', text)
        self.assertLess(
            text.index('ctrl_frame.pack(fill="x", pady=(0, 10), before=progress_section)'),
            text.index('self.btn_start = StyledButton'),
        )

    def test_subtitle_size_hint_explains_the_actual_auto_size(self):
        source = Path(__file__).resolve().parents[1] / "gui" / "app.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("self.subtitle_size_hint_label", text)
        self.assertIn("def _refresh_subtitle_size_hint", text)
        self.assertIn("单语≥{single_size}；中英双语≥{bilingual_size}；图片自动×{bitmap_scale:.2f}", text)


if __name__ == "__main__":
    unittest.main()
