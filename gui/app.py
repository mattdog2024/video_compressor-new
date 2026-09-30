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
from core.task_pool import TaskPool
from core.subtitle import format_subtitle_choice, select_embedded_subtitle_stream
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
        self.root.title("万能视频压缩器 v1.0.12")
        self.root.geometry("820x980")
        self.root.minsize(750, 820)
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
        self.engines: Dict[int, FFmpegEngine] = {}
        self.active_tasks: Dict[int, CompressTask] = {}
        self.task_pool = TaskPool(self.settings.get("parallel_tasks", 3))
        self._reserved_output_paths = set()
        self._cancel_requested = False

        # 文件管理
        self.file_counter = 0
        self.file_queue: Dict[int, str] = {}  # id -> path
        self.file_info: Dict[int, VideoInfo] = {}  # id -> info
        self.task_queue: List[int] = []  # 待处理的file_id列表
        self.current_task_index = 0
        # 每个文件单独保存选中的内置字幕流；缺省表示“自动选默认/第一条”。
        self._embedded_subtitle_selections: Dict[int, int] = {}
        self._subtitle_selection_controls: Dict[int, dict] = {}

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

        self.platform_compatibility_var = tk.BooleanVar(value=True)
        self.platform_compatibility_cb = tk.Checkbutton(
            row2, text="平台兼容模式（推荐）",
            variable=self.platform_compatibility_var,
            bg=DARK_THEME["surface"], fg=DARK_THEME["text"],
            selectcolor=DARK_THEME["entry_bg"],
            activebackground=DARK_THEME["surface"],
            activeforeground=DARK_THEME["text"],
            font=FONTS["body"]
        )
        self.platform_compatibility_cb.pack(side="left", padx=(15, 0))

        # 第三行 - 批量并行数
        parallel_row = tk.Frame(output_section, bg=DARK_THEME["surface"])
        parallel_row.pack(fill="x", padx=15, pady=(0, 8))

        self._create_label(parallel_row, "同时压缩:").pack(side="left")
        self.parallel_tasks_var = tk.StringVar(value="3")
        self.parallel_tasks_combo = ttk.Combobox(
            parallel_row, textvariable=self.parallel_tasks_var,
            values=["1", "2", "3"], state="readonly", width=5
        )
        self.parallel_tasks_combo.pack(side="left", padx=(5, 5))
        self._create_label(parallel_row, "个任务（最多 3 个）").pack(side="left")

        # 第四行 - 输出目录
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
            values=["无", "内置字幕（烧录）", "外挂字幕（烧录）"],
            state="readonly", width=12
        )
        self.subtitle_mode_combo.pack(side="left", padx=(5, 10))
        self.subtitle_mode_combo.bind("<<ComboboxSelected>>", self._on_subtitle_mode_change)

        # 内置字幕按文件分别选择。列表自身可滚动，视频多时不会挤掉开始压缩按钮。
        self.subtitle_selection_frame = tk.Frame(adv_section, bg=DARK_THEME["surface"])
        self._create_label(
            self.subtitle_selection_frame,
            "每个视频单独选择内置字幕（不选则自动使用默认字幕/第一条）：",
        ).pack(anchor="w", padx=2, pady=(0, 4))

        self.subtitle_selection_canvas = tk.Canvas(
            self.subtitle_selection_frame, bg=DARK_THEME["surface2"],
            highlightthickness=1, highlightbackground=DARK_THEME["border"],
            height=150, bd=0,
        )
        self.subtitle_selection_scrollbar = ttk.Scrollbar(
            self.subtitle_selection_frame, orient="vertical",
            command=self.subtitle_selection_canvas.yview,
        )
        self.subtitle_selection_canvas.configure(
            yscrollcommand=self.subtitle_selection_scrollbar.set,
        )
        self.subtitle_selection_rows = tk.Frame(
            self.subtitle_selection_canvas, bg=DARK_THEME["surface2"],
        )
        self._subtitle_selection_canvas_window = self.subtitle_selection_canvas.create_window(
            (0, 0), window=self.subtitle_selection_rows, anchor="nw",
        )
        self.subtitle_selection_rows.bind(
            "<Configure>", self._on_subtitle_rows_configure,
        )
        self.subtitle_selection_canvas.bind(
            "<Configure>", self._on_subtitle_canvas_configure,
        )
        self.subtitle_selection_canvas.pack(side="left", fill="both", expand=True)
        self.subtitle_selection_scrollbar.pack(side="right", fill="y")

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
        self._create_label(sub_row, "  字号（文字字幕最小值）:").pack(side="left")
        self.sub_font_size_var = tk.StringVar(value="42")
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
        self.subtitle_size_hint_label = tk.Label(
            sub_row, text="",
            bg=DARK_THEME["surface"], fg=DARK_THEME["text_muted"],
            font=FONTS["small"], anchor="w",
        )
        self.subtitle_size_hint_label.pack(side="left", padx=(8, 0))

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
        # 字幕详情会动态增加高级设置高度；把操作按钮插在进度区前面，
        # 窗口高度不足时也一定能看到“开始压缩 / 取消”。
        ctrl_frame.pack(fill="x", pady=(0, 10), before=progress_section)

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
        self.platform_compatibility_var.set(s.get("platform_compatibility", True))
        self.output_dir_var.set(s.get("last_output_dir", ""))
        self.after_complete_var.set(s.get("after_complete", "无操作"))

        sub_mode = s.get("subtitle_mode", "无")
        mode_map = {
            "none": "无", "embedded": "内置字幕（烧录）", "external": "外挂字幕（烧录）",
            "无": "无", "内置字幕": "内置字幕（烧录）", "外挂字幕": "外挂字幕（烧录）",
            "内置字幕（烧录）": "内置字幕（烧录）",
            "外挂字幕（烧录）": "外挂字幕（烧录）",
        }
        self.subtitle_mode_var.set(mode_map.get(sub_mode, "无"))
        self.parallel_tasks_var.set(str(max(1, min(3, self._safe_int(s.get("parallel_tasks", 3), 3)))))

        try:
            self.sub_font_size_var.set(str(s.get("subtitle_font_size", 42)))
        except (ValueError, TypeError):
            self.sub_font_size_var.set("42")
        self._refresh_subtitle_size_hint()
        self._on_subtitle_mode_change()

    def _save_settings_from_ui(self):
        """从UI保存设置"""
        mode_map = {
            "无": "none",
            "内置字幕（烧录）": "embedded",
            "外挂字幕（烧录）": "external",
        }
        self.settings.update({
            "resolution": self.resolution_var.get(),
            "quality": self.quality_var.get(),
            "audio_bitrate": self.audio_br_var.get(),
            "volume": self.volume_var.get(),
            "skip_start": self._safe_int(self.skip_start_var.get()),
            "skip_end": self._safe_int(self.skip_end_var.get()),
            "filename_suffix": self.suffix_var.get(),
            "remove_audio": self.remove_audio_var.get(),
            "platform_compatibility": self.platform_compatibility_var.get(),
            "parallel_tasks": max(1, min(3, self._safe_int(self.parallel_tasks_var.get(), 3))),
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
        if self.subtitle_mode_var.get() == "内置字幕（烧录）":
            self._update_subtitle_streams()

    def _clear_file_list(self):
        """清空文件列表"""
        if self.task_pool.has_work or self._has_running_tasks():
            messagebox.showinfo("提示", "请先停止当前压缩任务")
            return
        self.file_list.clear()
        self.file_queue.clear()
        self.file_info.clear()
        self.task_queue.clear()
        self._embedded_subtitle_selections.clear()
        if self.subtitle_mode_var.get() == "内置字幕（烧录）":
            self._update_subtitle_streams()
        self.task_pool.reset([])
        self._reserved_output_paths.clear()
        self.file_counter = 0
        self.current_task_index = 0
        self.progress_frame.reset()
        self.task_info_label.config(text="就绪")

    def _on_file_remove(self, file_id):
        """从列表中移除单个文件（×按钮回调）"""
        # 从各数据结构中移除
        self.file_queue.pop(file_id, None)
        self.file_info.pop(file_id, None)
        self._embedded_subtitle_selections.pop(file_id, None)
        if file_id in self.task_queue:
            self.task_queue.remove(file_id)
        if self.subtitle_mode_var.get() == "内置字幕（烧录）":
            self._update_subtitle_streams()
        logger.info(f"已移除文件 #{file_id}")

    def _on_resolution_changed(self, *args):
        """分辨率变化时自动更新文件名后缀"""
        res = self.resolution_var.get()
        if res == "原始分辨率":
            self.suffix_var.set("")
        else:
            # "480p" → "_480p", "720p" → "_720p" 等
            self.suffix_var.set(f"_{res}")
        self._refresh_subtitle_size_hint()

    def _refresh_subtitle_size_hint(self):
        """明确显示自动适应后的最低字号，避免界面值和实际渲染值不一致。"""
        if not hasattr(self, "subtitle_size_hint_label"):
            return
        resolution = self.resolution_var.get()
        target_height = RESOLUTION_MAP.get(resolution, RESOLUTION_MAP["720p"])["height"]
        if target_height <= 0:
            text = "文字使用填写字号；图片保持原大小"
        else:
            requested = self._safe_int(self.sub_font_size_var.get(), 42)
            text_size = FFmpegEngine._effective_text_subtitle_font_size(
                requested, resolution, target_height,
            )
            bitmap_scale = FFmpegEngine._bitmap_subtitle_scale_factor(
                resolution, target_height,
            )
            text = f"文字实际≥{text_size}；图片自动×{bitmap_scale:.2f}"
        self.subtitle_size_hint_label.config(text=text)

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
        self.subtitle_selection_frame.pack_forget()
        self.btn_load_sub.pack_forget()
        self.subtitle_file_label.pack_forget()

        if mode == "内置字幕（烧录）":
            # 显示每个文件各自的字幕流选择
            self._update_subtitle_streams()
            self.subtitle_selection_frame.pack(fill="x", padx=15, pady=(0, 8))
        elif mode == "外挂字幕（烧录）":
            self.btn_load_sub.pack(side="left", padx=(0, 10))
            self.subtitle_file_label.pack(side="left")

    def _update_subtitle_streams(self):
        """为队列中的每一个文件创建独立的内置字幕选择框。"""
        for child in self.subtitle_selection_rows.winfo_children():
            child.destroy()
        self._subtitle_selection_controls.clear()

        if not self.file_info:
            tk.Label(
                self.subtitle_selection_rows,
                text="请先添加视频；每个带内置字幕的视频会在这里出现独立选择项。",
                bg=DARK_THEME["surface2"], fg=DARK_THEME["text_muted"],
                font=FONTS["small"], anchor="w",
            ).pack(fill="x", padx=8, pady=8)
            return

        for fid, info in self.file_info.items():
            self._create_subtitle_selection_row(fid, info)

        self.subtitle_selection_canvas.yview_moveto(0)

    def _create_subtitle_selection_row(self, file_id: int, info: VideoInfo):
        """创建单个视频的字幕轨选择行，选择结果只绑定到这个文件。"""
        row = tk.Frame(self.subtitle_selection_rows, bg=DARK_THEME["surface2"])
        row.pack(fill="x", padx=6, pady=(5, 2))

        header = tk.Frame(row, bg=DARK_THEME["surface2"])
        header.pack(fill="x")
        display_name = info.file_name
        if len(display_name) > 38:
            display_name = f"{display_name[:18]}…{display_name[-17:]}"
        tk.Label(
            header, text=f"文件 {file_id}：{display_name}",
            bg=DARK_THEME["surface2"], fg=DARK_THEME["text"],
            font=FONTS["small"], anchor="w", width=42,
        ).pack(side="left")

        if not info.subtitle_streams:
            tk.Label(
                header, text="没有内置字幕（此文件不会烧录字幕）",
                bg=DARK_THEME["surface2"], fg=DARK_THEME["text_muted"],
                font=FONTS["small"], anchor="w",
            ).pack(side="left", fill="x", expand=True)
            self._embedded_subtitle_selections.pop(file_id, None)
            return

        default_stream = select_embedded_subtitle_stream(info.subtitle_streams)
        _, auto_detail = format_subtitle_choice(
            info.file_name, default_stream.ordinal, default_stream.index,
            default_stream.codec, default_stream.language, default_stream.title,
            default_stream.default,
        )
        choices = [
            (None, "自动（默认字幕 / 第一条）", f"自动选择：\n{auto_detail}"),
        ]
        for stream in info.subtitle_streams:
            short_label, detail = format_subtitle_choice(
                info.file_name, stream.ordinal, stream.index, stream.codec,
                stream.language, stream.title, stream.default,
            )
            choices.append((stream.index, short_label, detail))

        chosen_stream_index = self._embedded_subtitle_selections.get(file_id)
        selected_index = next(
            (index for index, item in enumerate(choices) if item[0] == chosen_stream_index),
            0,
        )
        selection_var = tk.StringVar(value=choices[selected_index][1])
        combo = ttk.Combobox(
            header, textvariable=selection_var,
            values=[item[1] for item in choices], state="readonly", width=32,
        )
        combo.current(selected_index)
        combo.pack(side="left", fill="x", expand=True, padx=(5, 0))

        detail_label = tk.Label(
            row, text=choices[selected_index][2], bg=DARK_THEME["surface2"],
            fg=DARK_THEME["text_muted"], font=FONTS["small"], anchor="w",
            justify="left", wraplength=700,
        )
        detail_label.pack(fill="x", padx=(10, 0), pady=(1, 2))
        self._subtitle_selection_controls[file_id] = {
            "combo": combo,
            "choices": choices,
            "detail": detail_label,
        }
        combo.bind(
            "<<ComboboxSelected>>",
            lambda event, fid=file_id: self._on_file_subtitle_stream_selected(fid),
        )

    def _on_file_subtitle_stream_selected(self, file_id: int):
        """保存一个文件自己的字幕轨，不影响队列里的其他视频。"""
        control = self._subtitle_selection_controls.get(file_id)
        if not control:
            return
        index = control["combo"].current()
        choices = control["choices"]
        if not 0 <= index < len(choices):
            return
        stream_index, _, detail = choices[index]
        self._set_embedded_subtitle_selection(file_id, stream_index)
        control["detail"].config(text=detail)

    def _set_embedded_subtitle_selection(self, file_id: int, stream_index: Optional[int]):
        """写入一个文件的字幕选择；None 表示恢复自动选择。"""
        info = self.file_info.get(file_id)
        if stream_index is None:
            self._embedded_subtitle_selections.pop(file_id, None)
            return
        if info and any(stream.index == stream_index for stream in info.subtitle_streams):
            self._embedded_subtitle_selections[file_id] = stream_index
        else:
            self._embedded_subtitle_selections.pop(file_id, None)

    def _on_subtitle_rows_configure(self, event=None):
        """刷新滚动区域高度。"""
        self.subtitle_selection_canvas.configure(
            scrollregion=self.subtitle_selection_canvas.bbox("all"),
        )

    def _on_subtitle_canvas_configure(self, event=None):
        """让内层选择行始终贴满滚动面板宽度。"""
        if event is not None:
            self.subtitle_selection_canvas.itemconfigure(
                self._subtitle_selection_canvas_window, width=event.width,
            )

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
        if self.task_pool.has_work or self._has_running_tasks():
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
        self._cancel_requested = False
        self.engines.clear()
        self.active_tasks.clear()
        self._reserved_output_paths.clear()
        self.task_pool.set_max_parallel_tasks(self.parallel_tasks_var.get())
        self.task_pool.reset(self.task_queue)
        self.progress_frame.reset()
        for fid in self.task_queue:
            self.file_list.update_status(fid, "等待中", DARK_THEME["warning"])
        self._start_available_tasks()

    def _start_available_tasks(self):
        """填满可用并行槽位，最多同时启动三个压缩任务。"""
        if self._cancel_requested:
            return
        self.task_pool.start_available(self._start_single_task)
        self._refresh_task_summary()

    def _start_single_task(self, fid: int):
        """启动单个压缩任务，由 TaskPool 控制同时运行数量。"""
        file_path = self.file_queue[fid]
        info = self.file_info[fid]

        # 生成输出路径
        output_dir = self.output_dir_var.get() or os.path.dirname(file_path)
        suffix = self.suffix_var.get() or "_720p"
        output_path = FFmpegEngine.generate_output_path(
            file_path, output_dir, suffix, self._reserved_output_paths
        )
        self._reserved_output_paths.add(output_path)

        # 创建任务
        task = CompressTask(
            task_id=fid,
            input_file=file_path,
            output_file=output_path,
        )

        # 构建选项
        options = self._build_options(fid)

        # 更新UI
        self.file_list.update_status(fid, "压缩中...", DARK_THEME["accent"])
        self.active_tasks[fid] = task
        engine = FFmpegEngine()
        self.engines[fid] = engine

        # 每个任务使用独立 FFmpegEngine，进度消息仍集中回到主线程更新界面。
        engine.start_task(
            task, options,
            total_duration=info.duration,
            source_height=info.video_height,
            on_progress=lambda t: self.msg_queue.put(("progress", t)),
            on_complete=lambda t: self.msg_queue.put(("complete", t)),
            on_error=lambda t: self.msg_queue.put(("error", t)),
        )

    def _build_options(self, file_id: int = None) -> CompressOptions:
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
        subtitle_stream_ordinal = -1
        subtitle_codec = ""
        external_sub_path = ""
        mode_str = self.subtitle_mode_var.get()
        if mode_str == "内置字幕（烧录）":
            selected_subtitle = self._get_embedded_subtitle_for_file(file_id)
            if selected_subtitle:
                subtitle_mode = "embedded"
                subtitle_stream_index = selected_subtitle.index
                subtitle_stream_ordinal = selected_subtitle.ordinal
                subtitle_codec = selected_subtitle.codec
            else:
                logger.info("文件没有可烧录的内置字幕: %s", file_id)
        elif mode_str == "外挂字幕（烧录）":
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
            platform_compatibility=self.platform_compatibility_var.get(),
            subtitle_mode=subtitle_mode,
            subtitle_stream_index=subtitle_stream_index,
            subtitle_stream_ordinal=subtitle_stream_ordinal,
            subtitle_codec=subtitle_codec,
            external_subtitle_path=external_sub_path,
            subtitle_font_size=self._safe_int(self.sub_font_size_var.get(), 24),
            subtitle_font_color="#FFFFFF",
            gpu_encoder=gpu_encoder,
        )

    def _get_embedded_subtitle_for_file(self, file_id: int):
        """获取一个文件应烧录的内置字幕：本文件指定条目优先，否则自动选择。"""
        info = self.file_info.get(file_id)
        if not info or not info.subtitle_streams:
            return None

        return select_embedded_subtitle_stream(
            info.subtitle_streams,
            self._embedded_subtitle_selections.get(file_id),
        )

    def _has_running_tasks(self) -> bool:
        """检查是否仍有实际运行中的 FFmpeg 进程。"""
        return any(engine.is_running() for engine in self.engines.values())

    def _refresh_task_summary(self):
        """刷新并行批处理摘要。"""
        active_count = len(self.task_pool.active)
        pending_count = len(self.task_pool.pending)
        total = len(self.task_queue)
        if active_count:
            self.task_info_label.config(
                text=(f"同时压缩 {active_count}/{self.task_pool.max_parallel_tasks} 个 | "
                      f"等待 {pending_count} 个 | 共 {total} 个")
            )

    def _cancel_compression(self):
        """取消等待和运行中的所有任务。"""
        if not self.task_pool.has_work and not self._has_running_tasks():
            return

        self._cancel_requested = True
        pending_ids = list(self.task_pool.pending)
        active_ids = self.task_pool.cancel()
        for fid in pending_ids:
            self.file_list.update_status(fid, "已取消", DARK_THEME["text_muted"])
        for fid in active_ids:
            self.file_list.update_status(fid, "取消中", DARK_THEME["text_muted"])
            engine = self.engines.get(fid)
            if engine:
                engine.cancel()
        self.active_tasks.clear()
        self.task_info_label.config(text="已取消本批压缩")
        self.status_bar.config(text="用户取消了等待和运行中的压缩任务")

    def _all_tasks_complete(self):
        """所有任务完成"""
        self.task_info_label.config(text="✓ 所有任务已完成！")
        self.status_bar.config(text="所有压缩任务已完成")

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
                    if not data.best_gpu:
                        self.status_bar.config(
                            text="提示：没有可用的GPU编码，极速模式会使用CPU，速度会比显卡加速慢"
                        )

                elif msg_type == "hw_error":
                    self.hw_label.config(text="硬件检测失败", fg=DARK_THEME["error"])

                elif msg_type == "progress":
                    task = data
                    if task.task_id in self.active_tasks:
                        # 进度条显示最近更新的一个任务；文件列表同时标出全部运行任务。
                        self.progress_frame.update_progress(task)
                        self.status_bar.config(
                            text=(f"压缩中: {os.path.basename(task.input_file)} "
                                  f"{task.progress:.1f}% | "
                                  f"并行 {len(self.task_pool.active)}/{self.task_pool.max_parallel_tasks}")
                        )

                elif msg_type == "complete":
                    task = data
                    self.task_pool.finish(task.task_id)
                    self.active_tasks.pop(task.task_id, None)
                    self.engines.pop(task.task_id, None)
                    self.progress_frame.update_progress(task)
                    self.file_list.update_status(task.task_id, "✓ 完成", DARK_THEME["success"])

                    size_info = ""
                    if task.output_size > 0:
                        input_info = self.file_info.get(task.task_id)
                        if input_info:
                            ratio = task.output_size / input_info.file_size * 100
                            size_info = f" | 压缩率: {ratio:.1f}% | 输出: {format_file_size(task.output_size)}"

                    fallback_info = ""
                    if task.fallback_note:
                        fallback_info = f" | {task.fallback_note}"

                    self.status_bar.config(
                        text=f"✓ 完成: {os.path.basename(task.output_file)}{size_info}{fallback_info}"
                    )
                    if not self._cancel_requested:
                        self._start_available_tasks()
                        if self.task_pool.is_idle:
                            self._all_tasks_complete()
                    else:
                        self._refresh_task_summary()

                elif msg_type == "error":
                    task = data
                    self.task_pool.finish(task.task_id)
                    self.active_tasks.pop(task.task_id, None)
                    self.engines.pop(task.task_id, None)
                    self.file_list.update_status(task.task_id, "✗ 失败", DARK_THEME["error"])
                    self.task_info_label.config(text=f"错误: {task.error_message[:100]}")
                    self.status_bar.config(text=f"压缩失败: {task.error_message[:80]}")
                    if not self._cancel_requested:
                        self._start_available_tasks()
                        if self.task_pool.is_idle:
                            self._all_tasks_complete()
                    else:
                        self._refresh_task_summary()

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
        if self.task_pool.has_work or self._has_running_tasks():
            self._cancel_compression()

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
