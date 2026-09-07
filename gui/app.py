"""主窗口应用"""
import os
import sys
import json
import threading
import queue
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, List, Dict

from gui.themes import DARK_THEME, FONTS
from gui.widgets import StyledButton, ProgressFrame, FileListWidget
from core.hardware import detect_hardware, get_encoder_choices, HardwareProfile
from core.probe import probe_video, VideoInfo
from core.ffmpeg_engine import (
    FFmpegEngine, CompressTask, CompressOptions, TaskStatus
)
from utils.helpers import (
    format_file_size, format_duration, format_time_remaining,
    load_settings, save_settings, get_default_settings,
    SUPPORTED_VIDEO_FORMATS, SUPPORTED_SUBTITLE_FORMATS,
    RESOLUTION_MAP, QUALITY_PRESETS,
)

logger = logging.getLogger(__name__)


class VideoCompressorApp:
    """万能视频压缩器主应用"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("万能视频压缩器 v9.0")
        self.root.geometry("820x900")
        self.root.minsize(750, 800)
        self.root.configure(bg=DARK_THEME["bg"])

        # 确保窗口有原生标题栏和控制按钮（最小化/最大化/关闭）
        self.root.attributes('-fullscreen', False)
        self.root.resizable(True, True)
        self.root.deiconify()

        # 窗口控制协议
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._closing = False

        # 状态
        self.settings = load_settings()
        self.hardware: Optional[HardwareProfile] = None
        self.encoder_choices: list = []
        self.engine = FFmpegEngine()

        # 文件管理
        self.file_counter = 0
        self.file_queue: Dict[int, str] = {}  # id -> path
        self.file_info: Dict[int, VideoInfo] = {}  # id -> info
        self.task_queue: List[int] = []  # 待处理的file_id列表
        self.current_task_index = 0

        # 消息队列（线程安全更新GUI）
        self.msg_queue = queue.Queue()
        self._last_progress_time = 0  # 上次进度更新时间戳
        self._last_progress_value = 0.0  # 上次进度值

        # 初始化
        self._setup_ui()
        self._detect_hardware_async()
        self._load_settings_to_ui()

        # 定时检查消息队列
        self._poll_messages()

    def _setup_ui(self):
        """构建界面"""
        # 主滚动区域
        main_frame = tk.Frame(self.root, bg=DARK_THEME["bg"])
        main_frame.pack(fill="both", expand=True, padx=15, pady=10)

        # === 标题 ===
        title_frame = tk.Frame(main_frame, bg=DARK_THEME["bg"])
        title_frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            title_frame, text="🎬 万能视频压缩器",
            bg=DARK_THEME["bg"], fg=DARK_THEME["accent"],
            font=FONTS["title"]
        ).pack(side="left")

        self.hw_label = tk.Label(
            title_frame, text="检测中...",
            bg=DARK_THEME["bg"], fg=DARK_THEME["text_muted"],
            font=FONTS["small"]
        )
        self.hw_label.pack(side="right")

        # === 文件列表区域 ===
        file_section = tk.LabelFrame(
            main_frame, text="",
            bg=DARK_THEME["surface"], fg=DARK_THEME["text"],
            highlightbackground=DARK_THEME["border"],
            highlightthickness=1
        )
        file_section.pack(fill="both", expand=False, pady=(0, 10))

        # 文件列表
        self.file_list = FileListWidget(file_section, on_remove=self._on_file_remove)
        self.file_list.pack(fill="both", expand=True, padx=5, pady=5)

        # 文件操作按钮
        file_btn_frame = tk.Frame(file_section, bg=DARK_THEME["surface"])
        file_btn_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.btn_add = StyledButton(
            file_btn_frame, text="+ 添加文件",
            command=self._add_files,
            width=120, height=32, radius=6
        )
        self.btn_add.pack(side="left")

        self.btn_add_folder = StyledButton(
            file_btn_frame, text="+ 添加文件夹",
            command=self._add_folder,
            bg_color=DARK_THEME["surface2"],
            hover_color=DARK_THEME["overlay"],
            fg_color=DARK_THEME["text"],
            width=130, height=32, radius=6
        )
        self.btn_add_folder.pack(side="left", padx=10)

        self.btn_clear_list = StyledButton(
            file_btn_frame, text="清空列表",
            command=self._clear_file_list,
            bg_color=DARK_THEME["surface2"],
            hover_color=DARK_THEME["overlay"],
            fg_color=DARK_THEME["text_muted"],
            width=100, height=32, radius=6
        )
        self.btn_clear_list.pack(side="right")

        # === 输出设置 ===
        output_section = tk.LabelFrame(
            main_frame, text="  输出设置  ",
            bg=DARK_THEME["surface"], fg=DARK_THEME["accent"],
            font=FONTS["heading"],
            highlightbackground=DARK_THEME["border"],
            highlightthickness=1
        )
        output_section.pack(fill="x", pady=(0, 10))

        # 第一行
        row1 = tk.Frame(output_section, bg=DARK_THEME["surface"])
        row1.pack(fill="x", padx=15, pady=8)

        self._create_label(row1, "分辨率:").pack(side="left")
        self.resolution_var = tk.StringVar(value="720p")
        self.resolution_combo = ttk.Combobox(
            row1, textvariable=self.resolution_var,
            values=list(RESOLUTION_MAP.keys()),
            state="readonly", width=12
        )
        self.resolution_combo.pack(side="left", padx=(5, 20))
        # 分辨率变化时自动更新文件名后缀
        self.resolution_var.trace_add("write", self._on_resolution_changed)

        self._create_label(row1, "质量:").pack(side="left")
        self.quality_var = tk.StringVar(value="标准")
        self.quality_combo = ttk.Combobox(
            row1, textvariable=self.quality_var,
            values=list(QUALITY_PRESETS.keys()),
            state="readonly", width=12
        )
        self.quality_combo.pack(side="left", padx=(5, 20))

        self._create_label(row1, "编码器:").pack(side="left")
        self.encoder_var = tk.StringVar(value="自动 (CPU)")
        self.encoder_combo = ttk.Combobox(
            row1, textvariable=self.encoder_var,
            state="readonly", width=20
        )
        self.encoder_combo.pack(side="left", padx=5)

        # 第二行
        row2 = tk.Frame(output_section, bg=DARK_THEME["surface"])
        row2.pack(fill="x", padx=15, pady=(0, 8))

        self._create_label(row2, "音频码率:").pack(side="left")
        self.audio_br_var = tk.StringVar(value="128k")
        self.audio_br_combo = ttk.Combobox(
            row2, textvariable=self.audio_br_var,
            values=["64k", "96k", "128k", "192k", "256k", "320k"],
            state="readonly", width=10
        )
        self.audio_br_combo.pack(side="left", padx=(5, 20))

        self._create_label(row2, "文件名后缀:").pack(side="left")
        self.suffix_var = tk.StringVar(value="_720p")
        self.suffix_entry = tk.Entry(
            row2, textvariable=self.suffix_var,
            bg=DARK_THEME["entry_bg"], fg=DARK_THEME["text"],
            insertbackground=DARK_THEME["text"],
            font=FONTS["body"], width=12,
            highlightthickness=1, highlightcolor=DARK_THEME["accent"],
            highlightbackground=DARK_THEME["border"],
            relief="flat"
        )
        self.suffix_entry.pack(side="left", padx=(5, 20))

        self.remove_audio_var = tk.BooleanVar(value=False)
        self.remove_audio_cb = tk.Checkbutton(
            row2, text="移除音频",
            variable=self.remove_audio_var,
            bg=DARK_THEME["surface"], fg=DARK_THEME["text"],
            selectcolor=DARK_THEME["entry_bg"],
            activebackground=DARK_THEME["surface"],
            activeforeground=DARK_THEME["text"],
            font=FONTS["body"]
        )
        self.remove_audio_cb.pack(side="left")

        # 第三行 - 输出目录
        row3 = tk.Frame(output_section, bg=DARK_THEME["surface"])
        row3.pack(fill="x", padx=15, pady=(0, 8))

        self._create_label(row3, "输出目录:").pack(side="left")
        self.output_dir_var = tk.StringVar(value="")
        self.output_dir_entry = tk.Entry(
            row3, textvariable=self.output_dir_var,
            bg=DARK_THEME["entry_bg"], fg=DARK_THEME["text"],
            insertbackground=DARK_THEME["text"],
            font=FONTS["body"],
            highlightthickness=1, highlightcolor=DARK_THEME["accent"],
            highlightbackground=DARK_THEME["border"],
            relief="flat"
        )
        self.output_dir_entry.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_browse = StyledButton(
            row3, text="浏览",
            command=self._browse_output_dir,
            bg_color=DARK_THEME["surface2"],
            hover_color=DARK_THEME["overlay"],
            fg_color=DARK_THEME["text"],
            width=60, height=28, radius=6
        )
        self.btn_browse.pack(side="right", padx=(5, 0))

        # === 高级设置 ===
        adv_section = tk.LabelFrame(
            main_frame, text="  高级设置  ",
            bg=DARK_THEME["surface"], fg=DARK_THEME["accent"],
            font=FONTS["heading"],
            highlightbackground=DARK_THEME["border"],
            highlightthickness=1
        )
        adv_section.pack(fill="x", pady=(0, 10))

        # 音量
        vol_row = tk.Frame(adv_section, bg=DARK_THEME["surface"])
        vol_row.pack(fill="x", padx=15, pady=8)

        self._create_label(vol_row, "🔊 音量:").pack(side="left")
        self.volume_var = tk.IntVar(value=100)
        self.volume_scale = tk.Scale(
            vol_row, from_=0, to=100, orient="horizontal",
            variable=self.volume_var,
            bg=DARK_THEME["surface"], fg=DARK_THEME["text"],
            troughcolor=DARK_THEME["surface2"],
            activebackground=DARK_THEME["accent"],
            highlightthickness=0, length=300,
            command=self._on_volume_change
        )
        self.volume_scale.pack(side="left", padx=10, fill="x", expand=True)

        self.volume_label = tk.Label(
            vol_row, text="100",
            bg=DARK_THEME["surface"], fg=DARK_THEME["accent"],
            font=FONTS["mono"], width=4
        )
        self.volume_label.pack(side="left")

        # 跳过
        skip_row = tk.Frame(adv_section, bg=DARK_THEME["surface"])
        skip_row.pack(fill="x", padx=15, pady=(0, 8))

        self._create_label(skip_row, "⏩ 跳过开头:").pack(side="left")
        self.skip_start_var = tk.StringVar(value="0")
        self.skip_start_entry = tk.Entry(
            skip_row, textvariable=self.skip_start_var,
            bg=DARK_THEME["entry_bg"], fg=DARK_THEME["text"],
            insertbackground=DARK_THEME["text"],
            font=FONTS["body"], width=8,
            highlightthickness=1, highlightcolor=DARK_THEME["accent"],
            highlightbackground=DARK_THEME["border"],
            relief="flat"
        )
        self.skip_start_entry.pack(side="left", padx=(5, 5))
        self._create_label(skip_row, "秒").pack(side="left", padx=(0, 25))

        self._create_label(skip_row, "跳过结尾:").pack(side="left")
        self.skip_end_var = tk.StringVar(value="0")
        self.skip_end_entry = tk.Entry(
            skip_row, textvariable=self.skip_end_var,
            bg=DARK_THEME["entry_bg"], fg=DARK_THEME["text"],
            insertbackground=DARK_THEME["text"],
            font=FONTS["body"], width=8,
            highlightthickness=1, highlightcolor=DARK_THEME["accent"],
            highlightbackground=DARK_THEME["border"],
            relief="flat"
        )
        self.skip_end_entry.pack(side="left", padx=(5, 5))
        self._create_label(skip_row, "秒").pack(side="left")

        # 字幕
        sub_row = tk.Frame(adv_section, bg=DARK_THEME["surface"])
        sub_row.pack(fill="x", padx=15, pady=(0, 8))

        self._create_label(sub_row, "📝 字幕:").pack(side="left")
        self.subtitle_mode_var = tk.StringVar(value="无")
        self.subtitle_mode_combo = ttk.Combobox(
            sub_row, textvariable=self.subtitle_mode_var,
            values=["无", "内置字幕", "外挂字幕"],
            state="readonly", width=12
        )
        self.subtitle_mode_combo.pack(side="left", padx=(5, 10))
        self.subtitle_mode_combo.bind("<<ComboboxSelected>>", self._on_subtitle_mode_change)

        # 字幕流选择（内置字幕时显示）
        self.subtitle_stream_var = tk.StringVar(value="")
        self.subtitle_stream_combo = ttk.Combobox(
            sub_row, textvariable=self.subtitle_stream_var,
            state="readonly", width=20
        )
        # 默认隐藏
        # self.subtitle_stream_combo.pack(side="left", padx=(0, 10))

        # 外挂字幕选择
        self.btn_load_sub = StyledButton(
            sub_row, text="加载字幕文件",
            command=self._load_external_subtitle,
            bg_color=DARK_THEME["surface2"],
            hover_color=DARK_THEME["overlay"],
            fg_color=DARK_THEME["text"],
            width=120, height=28, radius=6
        )
        # 默认隐藏

        self.subtitle_file_label = tk.Label(
            sub_row, text="",
            bg=DARK_THEME["surface"], fg=DARK_THEME["text_muted"],
            font=FONTS["small"]
        )

        # 字幕字体
        self._create_label(sub_row, "  字号:").pack(side="left")
        self.sub_font_size_var = tk.StringVar(value="24")
        self.sub_font_entry = tk.Entry(
            sub_row, textvariable=self.sub_font_size_var,
            bg=DARK_THEME["entry_bg"], fg=DARK_THEME["text"],
            insertbackground=DARK_THEME["text"],
            font=FONTS["body"], width=5,
            highlightthickness=1, highlightcolor=DARK_THEME["accent"],
            highlightbackground=DARK_THEME["border"],
            relief="flat"
        )
        self.sub_font_entry.pack(side="left", padx=5)

        # === 进度区域 ===
        progress_section = tk.LabelFrame(
            main_frame, text="  进度  ",
            bg=DARK_THEME["surface"], fg=DARK_THEME["accent"],
            font=FONTS["heading"],
            highlightbackground=DARK_THEME["border"],
            highlightthickness=1
        )
        progress_section.pack(fill="x", pady=(0, 10))

        self.progress_frame = ProgressFrame(progress_section)
        self.progress_frame.pack(fill="x", padx=10, pady=10)

        # 当前任务信息
        self.task_info_label = tk.Label(
            progress_section, text="就绪",
            bg=DARK_THEME["surface"], fg=DARK_THEME["text_muted"],
            font=FONTS["body"], anchor="w"
        )
        self.task_info_label.pack(fill="x", padx=15, pady=(0, 8))

        # === 控制按钮 ===
        ctrl_frame = tk.Frame(main_frame, bg=DARK_THEME["bg"])
        ctrl_frame.pack(fill="x")

        self.btn_start = StyledButton(
            ctrl_frame, text="▶ 开始压缩",
            command=self._start_compression,
            bg_color=DARK_THEME["success"],
            hover_color="#94e2d5",
            fg_color=DARK_THEME["bg"],
            width=140, height=40, radius=8
        )
        self.btn_start.pack(side="left")

        self.btn_cancel = StyledButton(
            ctrl_frame, text="■ 取消",
            command=self._cancel_compression,
            bg_color=DARK_THEME["error"],
            hover_color="#eba0ac",
            fg_color=DARK_THEME["bg"],
            width=100, height=40, radius=8
        )
        self.btn_cancel.pack(side="left", padx=10)

        # 完成后操作
        tk.Label(
            ctrl_frame, text="完成后:",
            bg=DARK_THEME["bg"], fg=DARK_THEME["text_muted"],
            font=FONTS["body"]
        ).pack(side="right", padx=(10, 5))

        self.after_complete_var = tk.StringVar(value="无操作")
        self.after_complete_combo = ttk.Combobox(
            ctrl_frame, textvariable=self.after_complete_var,
            values=["无操作", "关闭程序", "关机"],
            state="readonly", width=12
        )
        self.after_complete_combo.pack(side="right")

        # 状态栏
        self.status_bar = tk.Label(
            main_frame, text="就绪 | 拖拽文件到窗口 或 Ctrl+V 粘贴即可添加",
            bg=DARK_THEME["bg"], fg=DARK_THEME["overlay"],
            font=FONTS["small"], anchor="w"
        )
        self.status_bar.pack(fill="x", pady=(10, 0))

        # 启用拖拽（通过绑定事件模拟）
        self.root.drop_target_register = None  # placeholder
        self._setup_drag_drop()

    def _create_label(self, parent, text):
        """创建统一风格的标签"""
        return tk.Label(
            parent, text=text,
            bg=DARK_THEME["surface"], fg=DARK_THEME["text"],
            font=FONTS["body"]
        )

    def _setup_drag_drop(self):
        """设置拖拽支持 - 使用windnd实现Windows原生拖拽"""
        # 延迟hook，确保窗口完全映射后再注册拖拽
        self.root.after(500, self._try_hook_windnd)

        # 绑定Ctrl+V粘贴支持
        self.root.bind_all("<Control-v>", self._on_paste)
        self.root.bind_all("<Control-V>", self._on_paste)

    def _try_hook_windnd(self):
        """尝试hook windnd拖拽，失败时重试一次"""
        try:
            import windnd
            windnd.hook_dropfiles(self.root, func=self._on_drop_files_raw)
            logger.info("windnd拖拽功能已启用")
            self._windnd_available = True
            self.status_bar.config(text="就绪 | 拖拽文件到窗口 或 Ctrl+V 粘贴即可添加（拖拽已启用）")
        except ImportError:
            logger.info("windnd不可用，拖拽功能禁用")
            self._windnd_available = False
            self.status_bar.config(text="就绪 | 拖拽不可用，请用 [+ 添加文件] 按钮或 Ctrl+V 粘贴")
        except Exception as e:
            logger.warning(f"拖拽功能初始化失败: {e}，500ms后重试")
            self._windnd_available = False
            # 重试一次
            self.root.after(500, self._retry_hook_windnd)

    def _retry_hook_windnd(self):
        """重试hook windnd"""
        try:
            import windnd
            windnd.hook_dropfiles(self.root, func=self._on_drop_files_raw)
            logger.info("windnd拖拽功能重试成功")
            self._windnd_available = True
            self.status_bar.config(text="就绪 | 拖拽文件到窗口 或 Ctrl+V 粘贴即可添加（拖拽已启用）")
        except Exception as e:
            logger.warning(f"拖拽功能重试失败: {e}")
            self.status_bar.config(text="就绪 | 拖拽不可用，请用 [+ 添加文件] 按钮或 Ctrl+V 粘贴")

    def _on_drop_files_raw(self, *args):
        """windnd拖拽回调（可能在非主线程调用）
        windnd回调签名可能是 (count, file_list) 或 (file_list) 或直接是路径列表
        使用*args兼容所有情况
        """
        logger.info(f"拖拽回调触发，参数: {len(args)} 个")

        # 解析参数
        file_list = []
        if len(args) == 2:
            # (count, file_list) 格式
            file_list = args[1] if isinstance(args[1], (list, tuple)) else args[0]
        elif len(args) == 1:
            arg = args[0]
            if isinstance(arg, (list, tuple)):
                file_list = arg
            else:
                file_list = [arg]
        else:
            return

        # windnd在Windows上返回的是字节列表
        paths = []
        for f in file_list:
            if isinstance(f, bytes):
                try:
                    paths.append(f.decode('utf-8'))
                except UnicodeDecodeError:
                    paths.append(f.decode('gbk', errors='replace'))
            else:
                paths.append(str(f))

        logger.info(f"拖拽解析到 {len(paths)} 个路径: {paths}")

        if paths:
            # 通过消息队列在主线程处理，确保线程安全
            self.msg_queue.put(("drop_files", paths))

    def _on_paste(self, event=None):
        """处理Ctrl+V粘贴文件"""
        try:
            # 从剪贴板获取文件路径
            clipboard = self.root.clipboard_get()
            if clipboard and os.path.exists(clipboard.split('\n')[0].strip()):
                for line in clipboard.strip().split('\n'):
                    path = line.strip()
                    if os.path.isfile(path):
                        self._enqueue_file(path)
                    elif os.path.isdir(path):
                        self._add_folder_path(path)
        except tk.TclError:
            pass  # 剪贴板没有文本内容

    def _add_folder_path(self, folder: str):
        """添加文件夹中的视频文件"""
        video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv',
                      '.webm', '.ts', '.m2ts', '.mpg', '.mpeg', '.3gp', '.vob', '.m4v'}
        for root_dir, dirs, files in os.walk(folder):
            for f in files:
                if os.path.splitext(f)[1].lower() in video_exts:
                    self._enqueue_file(os.path.join(root_dir, f))

    def _detect_hardware_async(self):
        """异步检测硬件"""
        def _detect():
            try:
                profile = detect_hardware()
                self.msg_queue.put(("hw_detected", profile))
            except Exception as e:
                logger.error(f"硬件检测失败: {e}")
                self.msg_queue.put(("hw_error", str(e)))

        threading.Thread(target=_detect, daemon=True).start()

    def _load_settings_to_ui(self):
        """从设置加载到UI"""
        s = self.settings
        self.resolution_var.set(s.get("resolution", "720p"))
        self.quality_var.set(s.get("quality", "标准"))
        self.audio_br_var.set(s.get("audio_bitrate", "128k"))
        self.volume_var.set(s.get("volume", 100))
        self.volume_label.config(text=str(s.get("volume", 100)))
        self.skip_start_var.set(str(s.get("skip_start", 0)))
        self.skip_end_var.set(str(s.get("skip_end", 0)))
        self.suffix_var.set(s.get("filename_suffix", "_720p"))
        self.remove_audio_var.set(s.get("remove_audio", False))
        self.output_dir_var.set(s.get("last_output_dir", ""))
        self.after_complete_var.set(s.get("after_complete", "无操作"))

        sub_mode = s.get("subtitle_mode", "无")
        mode_map = {"none": "无", "embedded": "内置字幕", "external": "外挂字幕",
                    "无": "无", "内置字幕": "内置字幕", "外挂字幕": "外挂字幕"}
        self.subtitle_mode_var.set(mode_map.get(sub_mode, "无"))

        try:
            self.sub_font_size_var.set(str(s.get("subtitle_font_size", 24)))
        except (ValueError, TypeError):
            self.sub_font_size_var.set("24")

    def _save_settings_from_ui(self):
        """从UI保存设置"""
        mode_map = {"无": "none", "内置字幕": "embedded", "外挂字幕": "external"}
        self.settings.update({
            "resolution": self.resolution_var.get(),
            "quality": self.quality_var.get(),
            "audio_bitrate": self.audio_br_var.get(),
            "volume": self.volume_var.get(),
            "skip_start": self._safe_int(self.skip_start_var.get()),
            "skip_end": self._safe_int(self.skip_end_var.get()),
            "filename_suffix": self.suffix_var.get(),
            "remove_audio": self.remove_audio_var.get(),
            "last_output_dir": self.output_dir_var.get(),
            "after_complete": self.after_complete_var.get(),
            "subtitle_mode": mode_map.get(self.subtitle_mode_var.get(), "none"),
            "subtitle_font_size": self._safe_int(self.sub_font_size_var.get(), 24),
        })
        save_settings(self.settings)

    # === 事件处理 ===

    def _add_files(self):
        """添加文件"""
        files = filedialog.askopenfilenames(
            title="选择视频文件",
            filetypes=SUPPORTED_VIDEO_FORMATS
        )
        for f in files:
            self._enqueue_file(f)

    def _add_folder(self):
        """添加文件夹"""
        folder = filedialog.askdirectory(title="选择文件夹")
        if not folder:
            return
        video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv',
                      '.webm', '.ts', '.m2ts', '.mpg', '.mpeg', '.3gp', '.vob', '.m4v'}
        for root, dirs, files in os.walk(folder):
            for f in files:
                if os.path.splitext(f)[1].lower() in video_exts:
                    self._enqueue_file(os.path.join(root, f))

    def _enqueue_file(self, file_path: str):
        """将文件加入队列"""
        # 探测视频信息
        info = probe_video(file_path)
        if info is None:
            messagebox.showwarning("警告", f"无法读取文件信息:\n{file_path}")
            return

        self.file_counter += 1
        fid = self.file_counter
        self.file_queue[fid] = file_path
        self.file_info[fid] = info

        file_info_str = f"{info.resolution_str} | {info.file_size_str} | {info.duration_str}"
        self.file_list.add_file(fid, info.file_name, file_info_str)

        self.status_bar.config(
            text=f"已添加: {info.file_name} ({info.resolution_str}, {info.file_size_str})"
        )

    def _clear_file_list(self):
        """清空文件列表"""
        if self.engine.is_running():
            messagebox.showinfo("提示", "请先停止当前压缩任务")
            return
        self.file_list.clear()
        self.file_queue.clear()
        self.file_info.clear()
        self.task_queue.clear()
        self.file_counter = 0
        self.current_task_index = 0
        self.progress_frame.reset()
        self.task_info_label.config(text="就绪")

    def _on_file_remove(self, file_id):
        """从列表中移除单个文件（×按钮回调）"""
        # 从各数据结构中移除
        self.file_queue.pop(file_id, None)
        self.file_info.pop(file_id, None)
        if file_id in self.task_queue:
            self.task_queue.remove(file_id)
        logger.info(f"已移除文件 #{file_id}")

    def _on_resolution_changed(self, *args):
        """分辨率变化时自动更新文件名后缀"""
        res = self.resolution_var.get()
        if res == "原始分辨率":
            self.suffix_var.set("")
        else:
            # "480p" → "_480p", "720p" → "_720p" 等
            self.suffix_var.set(f"_{res}")

    def _browse_output_dir(self):
        """浏览输出目录"""
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.output_dir_var.set(d)

    def _on_volume_change(self, value):
        """音量变化"""
        self.volume_label.config(text=str(int(float(value))))

    def _on_subtitle_mode_change(self, event=None):
        """字幕模式切换"""
        mode = self.subtitle_mode_var.get()

        # 隐藏所有字幕相关控件
        self.subtitle_stream_combo.pack_forget()
        self.btn_load_sub.pack_forget()
        self.subtitle_file_label.pack_forget()

        if mode == "内置字幕":
            # 显示字幕流选择
            self._update_subtitle_streams()
            self.subtitle_stream_combo.pack(side="left", padx=(0, 10))
        elif mode == "外挂字幕":
            self.btn_load_sub.pack(side="left", padx=(0, 10))
            self.subtitle_file_label.pack(side="left")

    def _update_subtitle_streams(self):
        """更新内置字幕流列表"""
        streams = []
        for fid, info in self.file_info.items():
            if info.has_subtitle:
                for sub in info.subtitle_streams:
                    lang = sub.language or "未知"
                    title = f" - {sub.title}" if sub.title else ""
                    label = f"{info.file_name}: [{sub.index}] {sub.codec} ({lang}{title})"
                    streams.append((fid, sub.index, label))

        if streams:
            labels = [s[2] for s in streams]
            self.subtitle_stream_combo["values"] = labels
            self.subtitle_stream_combo.current(0)
            self._subtitle_streams_data = streams
        else:
            self.subtitle_stream_combo["values"] = ["未检测到内置字幕"]
            self.subtitle_stream_combo.current(0)
            self._subtitle_streams_data = []

    def _load_external_subtitle(self):
        """加载外挂字幕文件"""
        f = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=SUPPORTED_SUBTITLE_FORMATS
        )
        if f:
            self._external_subtitle_path = f
            self.subtitle_file_label.config(text=os.path.basename(f))
            self.status_bar.config(text=f"已加载字幕: {os.path.basename(f)}")

    def _start_compression(self):
        """开始压缩"""
        if self.engine.is_running():
            messagebox.showinfo("提示", "已有任务正在运行")
            return

        if not self.file_queue:
            messagebox.showwarning("提示", "请先添加视频文件")
            return

        # 保存设置
        self._save_settings_from_ui()

        # 构建任务队列
        self.task_queue = list(self.file_queue.keys())
        self.current_task_index = 0

        # 开始处理第一个
        self._process_next_task()

    def _process_next_task(self):
        """处理队列中的下一个任务"""
        if self.current_task_index >= len(self.task_queue):
            self._all_tasks_complete()
            return

        fid = self.task_queue[self.current_task_index]
        file_path = self.file_queue[fid]
        info = self.file_info[fid]

        # 生成输出路径
        output_dir = self.output_dir_var.get() or os.path.dirname(file_path)
        suffix = self.suffix_var.get() or "_720p"
        output_path = FFmpegEngine.generate_output_path(file_path, output_dir, suffix)

        # 创建任务
        task = CompressTask(
            task_id=fid,
            input_file=file_path,
            output_file=output_path,
        )

        # 构建选项
        options = self._build_options()

        # 更新UI
        self.file_list.update_status(fid, "压缩中...", DARK_THEME["accent"])
        self.task_info_label.config(
            text=f"[{self.current_task_index + 1}/{len(self.task_queue)}] {info.file_name} → {os.path.basename(output_path)}"
        )
        self.progress_frame.reset()

        # 更新所有文件状态
        for i, qfid in enumerate(self.task_queue):
            if i < self.current_task_index:
                self.file_list.update_status(qfid, "✓ 完成", DARK_THEME["success"])
            elif i > self.current_task_index:
                self.file_list.update_status(qfid, "等待中", DARK_THEME["warning"])

        # 重置进度停滞检测
        import time as _time
        self._last_progress_time = _time.time()
        self._last_progress_value = 0.0

        # 启动引擎
        self.engine.start_task(
            task, options,
            total_duration=info.duration,
            source_height=info.video_height,
            on_progress=lambda t: self.msg_queue.put(("progress", t)),
            on_complete=lambda t: self.msg_queue.put(("complete", t)),
            on_error=lambda t: self.msg_queue.put(("error", t)),
        )

    def _build_options(self) -> CompressOptions:
        """从UI构建压缩选项"""
        # 解析编码器
        encoder_val = self.encoder_var.get()
        gpu_encoder = ""
        encoder_name = "libx264"

        if self.hardware:
            for display, name in self.encoder_choices:
                if display == encoder_val or encoder_val.startswith("自动"):
                    if encoder_val.startswith("自动") and self.hardware.best_gpu:
                        gpu_encoder = self.hardware.best_gpu.name
                        encoder_name = gpu_encoder
                    elif not encoder_val.startswith("自动"):
                        encoder_name = name
                        if self.hardware.best_gpu and name == self.hardware.best_gpu.name:
                            gpu_encoder = name
                    break

        # 字幕选项
        subtitle_mode = "none"
        subtitle_stream_index = -1
        external_sub_path = ""
        mode_str = self.subtitle_mode_var.get()
        if mode_str == "内置字幕":
            subtitle_mode = "embedded"
            if hasattr(self, '_subtitle_streams_data') and self._subtitle_streams_data:
                idx = self.subtitle_stream_combo.current()
                if idx >= 0 and idx < len(self._subtitle_streams_data):
                    subtitle_stream_index = self._subtitle_streams_data[idx][1]
        elif mode_str == "外挂字幕":
            subtitle_mode = "external"
            external_sub_path = getattr(self, '_external_subtitle_path', '')

        return CompressOptions(
            resolution=self.resolution_var.get(),
            quality=self.quality_var.get(),
            encoder=encoder_name,
            audio_bitrate=self.audio_br_var.get(),
            volume=self.volume_var.get(),
            skip_start=self._safe_float(self.skip_start_var.get()),
            skip_end=self._safe_float(self.skip_end_var.get()),
            remove_audio=self.remove_audio_var.get(),
            subtitle_mode=subtitle_mode,
            subtitle_stream_index=subtitle_stream_index,
            external_subtitle_path=external_sub_path,
            subtitle_font_size=self._safe_int(self.sub_font_size_var.get(), 24),
            subtitle_font_color="#FFFFFF",
            gpu_encoder=gpu_encoder,
        )

    def _cancel_compression(self):
        """取消压缩"""
        if self.engine.is_running():
            self.engine.cancel()
            self.task_info_label.config(text="已取消")
            self.status_bar.config(text="用户取消了压缩任务")

    def _all_tasks_complete(self):
        """所有任务完成"""
        self.task_info_label.config(text="✓ 所有任务已完成！")
        self.status_bar.config(text="所有压缩任务已完成")

        # 更新最后一个状态
        for fid in self.task_queue:
            self.file_list.update_status(fid, "✓ 完成", DARK_THEME["success"])

        # 完成后操作
        action = self.after_complete_var.get()
        if action == "关闭程序":
            self.root.after(2000, self._on_close)
        elif action == "关机":
            self.status_bar.config(text="将在60秒后关机...")
            if os.name == 'nt':
                os.system("shutdown /s /t 60")

    # === 消息队列处理 ===

    def _poll_messages(self):
        """轮询消息队列，更新GUI"""
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()

                if msg_type == "hw_detected":
                    self.hardware = data
                    self.encoder_choices = get_encoder_choices(data)
                    choices_display = [c[0] for c in self.encoder_choices]
                    self.encoder_combo["values"] = choices_display
                    if choices_display:
                        self.encoder_combo.current(0)

                    gpu_info = "无GPU加速"
                    if data.best_gpu:
                        gpu_info = f"GPU: {data.best_gpu.gpu_brand} ({data.best_gpu.display_name})"
                    self.hw_label.config(
                        text=f"FFmpeg {data.ffmpeg_version} | {gpu_info}",
                        fg=DARK_THEME["success"] if data.best_gpu else DARK_THEME["warning"]
                    )

                elif msg_type == "hw_error":
                    self.hw_label.config(text="硬件检测失败", fg=DARK_THEME["error"])

                elif msg_type == "progress":
                    task = data
                    self.progress_frame.update_progress(task)
                    import time as _time
                    now = _time.time()
                    # 记录进度值最后变化的时间
                    if abs(task.progress - self._last_progress_value) > 0.01:
                        self._last_progress_value = task.progress
                        self._last_progress_time = now

                    # 如果进度>=99%且超过15秒进度值没有变化，检查输出文件是否已生成
                    if task.progress >= 99.0 and (now - self._last_progress_time) > 15:
                        if os.path.exists(task.output_file):
                            # 文件已存在，FFmpeg可能卡在最终封装阶段
                            task.progress = 100.0
                            task.status = TaskStatus.COMPLETED
                            task.output_size = os.path.getsize(task.output_file)
                            self.msg_queue.put(("complete", task))

                elif msg_type == "complete":
                    task = data
                    self.progress_frame.update_progress(task)
                    self.file_list.update_status(task.task_id, "✓ 完成", DARK_THEME["success"])

                    size_info = ""
                    if task.output_size > 0:
                        input_info = self.file_info.get(task.task_id)
                        if input_info:
                            ratio = task.output_size / input_info.file_size * 100
                            size_info = f" | 压缩率: {ratio:.1f}% | 输出: {format_file_size(task.output_size)}"

                    self.status_bar.config(
                        text=f"✓ 完成: {os.path.basename(task.output_file)}{size_info}"
                    )

                    # 处理下一个
                    self.current_task_index += 1
                    self.root.after(500, self._process_next_task)

                elif msg_type == "error":
                    task = data
                    self.file_list.update_status(task.task_id, "✗ 失败", DARK_THEME["error"])
                    self.task_info_label.config(text=f"错误: {task.error_message[:100]}")
                    self.status_bar.config(text=f"压缩失败: {task.error_message[:80]}")

                    # 尝试下一个
                    self.current_task_index += 1
                    self.root.after(500, self._process_next_task)

                elif msg_type == "drop_files":
                    # 处理拖拽进来的文件
                    paths = data
                    added = 0
                    for p in paths:
                        if os.path.isfile(p):
                            video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv',
                                          '.webm', '.ts', '.m2ts', '.mpg', '.mpeg', '.3gp', '.vob', '.m4v'}
                            if os.path.splitext(p)[1].lower() in video_exts:
                                self._enqueue_file(p)
                                added += 1
                        elif os.path.isdir(p):
                            before = self.file_counter
                            self._add_folder_path(p)
                            added += self.file_counter - before
                    if added > 0:
                        self.status_bar.config(text=f"已拖入添加 {added} 个文件")

        except queue.Empty:
            pass

        self.root.after(100, self._poll_messages)

    # === 工具方法 ===

    @staticmethod
    def _safe_int(value, default=0):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _on_close(self):
        """窗口关闭事件"""
        if self._closing:
            return
        self._closing = True

        # 如果有正在运行的任务，先取消
        if self.engine.is_running():
            self.engine.cancel()

        # 保存设置
        try:
            self._save_settings_from_ui()
        except Exception:
            pass

        self.root.destroy()

    def run(self):
        """启动应用"""
        # 设置窗口图标（如果有的话）
        try:
            from utils.helpers import get_resource_path
            icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
            if os.path.exists(str(icon_path)):
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass

        # 居中显示
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.update_idletasks()

        self.root.mainloop()
