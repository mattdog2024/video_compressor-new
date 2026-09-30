"""Windows 打包版内置 ASS 字幕标准化回归测试。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.subtitle import _is_windows, prepare_clean_embedded_text_subtitle


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
class EmbeddedAssNormalizationTests(unittest.TestCase):
    def test_windows_helper_is_defined_and_uses_os_name(self):
        self.assertIsInstance(_is_windows(), bool)
        with patch("core.subtitle.os.name", "nt"):
            self.assertTrue(_is_windows())
        with patch("core.subtitle.os.name", "posix"):
            self.assertFalse(_is_windows())

    def test_ass_is_converted_to_clean_srt_before_rendering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            work = Path(temp_dir)
            ass_file = work / "styled.ass"
            video_file = work / "source.mkv"
            output_dir = work / "prepared"
            ass_file.write_text(
                "[Script Info]\n"
                "ScriptType: v4.00+\n"
                "[V4+ Styles]\n"
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
                "Style: Default,Arial,16,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,24,1\n"
                "[Events]\n"
                "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
                "Dialogue: 0,0:00:00.00,0:00:01.80,Default,,0,0,0,,{\\fs12\\bord6}重要的字幕\\N{\\fs9}不能很小\n",
                encoding="utf-8",
            )
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=2",
                "-i", str(ass_file), "-map", "0:v:0", "-map", "1:s:0",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:s", "ass",
                "-shortest", str(video_file),
            ], check=True, capture_output=True, text=True)

            cleaned = prepare_clean_embedded_text_subtitle(str(video_file), 1, str(output_dir))
            self.assertIsNotNone(cleaned)
            content = Path(cleaned).read_text(encoding="utf-8")
            self.assertIn("重要的字幕", content)
            self.assertIn("不能很小", content)
            self.assertNotIn("\\fs", content)
            self.assertNotIn("\\bord", content)


if __name__ == "__main__":
    unittest.main()
