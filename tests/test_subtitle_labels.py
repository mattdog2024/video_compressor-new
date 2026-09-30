"""字幕选择短名称与完整信息的回归测试。"""
import unittest

from core.subtitle import format_subtitle_choice, subtitle_kind_label


class SubtitleLabelTests(unittest.TestCase):
    def test_image_subtitle_kind_is_human_readable(self):
        self.assertEqual(subtitle_kind_label("hdmv_pgs_subtitle"), "PGS 图片字幕")
        self.assertEqual(subtitle_kind_label("dvd_subtitle"), "图片字幕")

    def test_long_title_stays_in_detail_instead_of_combobox_label(self):
        long_title = "至尊字幕:Marty.Supreme.2025.2160p.WEB-DL.DV.HDR.HEVC"
        short_label, detail = format_subtitle_choice(
            "Marty.Supreme.2025.mkv", 2, 7, "hdmv_pgs_subtitle",
            "chi", long_title, True, 1920, 1080,
        )
        self.assertEqual(short_label, "第3条 · chi · PGS 图片字幕")
        self.assertIn("完整名称：" + long_title, detail)
        self.assertIn("流 #7", detail)
        self.assertIn("默认字幕", detail)
        self.assertIn("画布 1920×1080", detail)


if __name__ == "__main__":
    unittest.main()
