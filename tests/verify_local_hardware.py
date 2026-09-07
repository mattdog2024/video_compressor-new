"""在Windows电脑上打印实际可用的硬件编码器。"""
from core.hardware import detect_hardware

profile = detect_hardware()
print("BEST_GPU=", profile.best_gpu.name if profile.best_gpu else "none")
print("BEST_CPU=", profile.best_cpu.name if profile.best_cpu else "none")
print("GPU_ENCODERS=", ",".join(item.name for item in profile.gpu_encoders) or "none")
print("DETECTION_LOG_START")
print(profile.detection_log)
print("DETECTION_LOG_END")
