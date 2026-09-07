"""硬件编码可用性与CPU回退的回归测试。"""
import subprocess
import unittest
from unittest.mock import patch

from core.ffmpeg_engine import CompressOptions, CompressTask, FFmpegEngine, TaskStatus
from core.hardware import detect_hardware


class HardwareDetectionTests(unittest.TestCase):
    @patch("core.hardware.subprocess.run")
    def test_listed_but_unusable_nvenc_is_not_offered(self, run_mock):
        """FFmpeg编译进NVENC但驱动不兼容时，应只提供CPU选项。"""
        run_mock.side_effect = [
            subprocess.CompletedProcess([], 0, "ffmpeg version test-build\n", ""),
            subprocess.CompletedProcess(
                [], 0,
                "Encoders:\n V..... h264_nvenc NVIDIA NVENC H.264 encoder\n"
                " V..... libx264 libx264 H.264 encoder\n",
                "",
            ),
            subprocess.CompletedProcess(
                [], 1, "",
                "Driver does not support the required nvenc API version.\n",
            ),
        ]

        profile = detect_hardware()

        self.assertIsNone(profile.best_gpu)
        self.assertEqual([encoder.name for encoder in profile.gpu_encoders], [])
        self.assertEqual(profile.best_cpu.name, "libx264")
        self.assertIn("GPU编码器不可用", profile.detection_log)


class GPUFallbackTests(unittest.TestCase):
    def make_task(self):
        return CompressTask(1, "input.mp4", "output.mp4")

    def test_gpu_failure_retries_once_with_cpu(self):
        engine = FFmpegEngine()
        task = self.make_task()
        completed = []
        engine._on_complete = completed.append
        calls = []

        def fake_execute(command, current_task, duration):
            calls.append(command)
            if len(calls) == 1:
                return 1, "Driver does not support the required nvenc API version."
            return 0, ""

        engine._execute_process = fake_execute
        engine._run_process(
            ["ffmpeg", "-c:v", "h264_nvenc"], task, 10,
            CompressOptions(encoder="h264_nvenc"), 720,
        )

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.fallback_note, "GPU编码不可用，已自动改用CPU编码")
        self.assertEqual(completed, [task])
        self.assertEqual(len(calls), 2)
        self.assertIn("libx264", calls[1])

    def test_cpu_failure_does_not_loop(self):
        engine = FFmpegEngine()
        task = self.make_task()
        errors = []
        engine._on_error = errors.append
        calls = []

        def fake_execute(command, current_task, duration):
            calls.append(command)
            return 1, "CPU encoder failed"

        engine._execute_process = fake_execute
        engine._run_process(
            ["ffmpeg", "-c:v", "libx264"], task, 10,
            CompressOptions(encoder="libx264"), 720,
        )

        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(len(calls), 1)
        self.assertEqual(errors, [task])
        self.assertEqual(task.error_message, "CPU encoder failed")


if __name__ == "__main__":
    unittest.main()
