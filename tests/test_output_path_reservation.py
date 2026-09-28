"""并行任务输出路径预留的回归测试。"""
import tempfile
import unittest
from pathlib import Path

from core.ffmpeg_engine import FFmpegEngine


class OutputPathReservationTests(unittest.TestCase):
    def test_reserved_path_prevents_parallel_name_collision(self):
        """同名输入在同一输出目录并发时，第二个任务必须自动改名。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            reserved = set()
            first = FFmpegEngine.generate_output_path(
                "/source_a/clip.mkv", str(output_dir), "_720p", reserved
            )
            reserved.add(first)
            second = FFmpegEngine.generate_output_path(
                "/source_b/clip.mp4", str(output_dir), "_720p", reserved
            )

            self.assertEqual(Path(first).name, "clip_720p.mp4")
            self.assertEqual(Path(second).name, "clip_720p_1.mp4")
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
