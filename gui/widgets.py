"""自定义控件"""
import tkinter as tk
from tkinter import ttk
from gui.themes import DARK_THEME, FONTS


class StyledButton(tk.Canvas):
    """自定义圆角按钮"""

    def __init__(self, parent, text="", command=None, bg_color=None,
                 fg_color=None, hover_color=None, font=None,
                 width=120, height=36, radius=8, **kwargs):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bg=parent.cget("bg") if hasattr(parent, 'cget') else DARK_THEME["bg"],
                         **kwargs)
        self._text = text
        self._command = command
        self._bg = bg_color or DARK_THEME["button_bg"]
        self._fg = fg_color or DARK_THEME["button_fg"]
        self._hover = hover_color or DARK_THEME["button_hover"]
        self._font = font or FONTS["body"]
        self._radius = radius
        self._width = width
        self._height = height
        self._disabled = False

        self._draw(self._bg)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _draw(self, fill_color):
        """绘制圆角矩形和文字"""
        self.delete("all")
        r = self._radius
        w, h = self._width, self._height

        # 圆角矩形
        self.create_arc(0, 0, r*2, r*2, start=90, extent=90, fill=fill_color, outline="")
        self.create_arc(w-r*2, 0, w, r*2, start=0, extent=90, fill=fill_color, outline="")
        self.create_arc(0, h-r*2, r*2, h, start=180, extent=90, fill=fill_color, outline="")
        self.create_arc(w-r*2, h-r*2, w, h, start=270, extent=90, fill=fill_color, outline="")
        self.create_rectangle(r, 0, w-r, h, fill=fill_color, outline="")
        self.create_rectangle(0, r, w, h-r, fill=fill_color, outline="")

        # 文字
        text_color = self._fg if not self._disabled else DARK_THEME["overlay"]
        self.create_text(w//2, h//2, text=self._text, fill=text_color,
                         font=self._font)

    def _on_enter(self, event):
        if not self._disabled:
            self._draw(self._hover)

    def _on_leave(self, event):
        if not self._disabled:
            self._draw(self._bg)

    def _on_click(self, event):
        if not self._disabled and self._command:
            self._command()

    def configure(self, **kwargs):
        if "text" in kwargs:
            self._text = kwargs.pop("text")
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._disabled = (state == "disabled")
        if "bg_color" in kwargs:
            self._bg = kwargs.pop("bg_color")
        super().configure(**kwargs)
        self._draw(self._bg if not self._disabled else DARK_THEME["surface2"])

    def set_text(self, text):
        self._text = text
        self._draw(self._bg)


class ProgressFrame(tk.Frame):
    """进度显示框架"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=DARK_THEME["bg"], **kwargs)
        self._setup_ui()

    def _setup_ui(self):
        # 进度条
        self.progress_bar = ttk.Progressbar(
            self, orient="horizontal", mode="determinate",
            length=500, maximum=100
        )
        self.progress_bar.pack(fill="x", padx=5, pady=(5, 2))

        # 信息行
        info_frame = tk.Frame(self, bg=DARK_THEME["bg"])
        info_frame.pack(fill="x", padx=5, pady=(0, 5))

        self.percent_label = tk.Label(
            info_frame, text="0%", bg=DARK_THEME["bg"],
            fg=DARK_THEME["accent"], font=FONTS["mono_small"]
        )
        self.percent_label.pack(side="left")

        self.speed_label = tk.Label(
            info_frame, text="速度: --", bg=DARK_THEME["bg"],
            fg=DARK_THEME["text_muted"], font=FONTS["mono_small"]
        )
        self.speed_label.pack(side="left", padx=20)

        self.time_label = tk.Label(
            info_frame, text="剩余: --", bg=DARK_THEME["bg"],
            fg=DARK_THEME["text_muted"], font=FONTS["mono_small"]
        )
        self.time_label.pack(side="right")

        self.elapsed_label = tk.Label(
            info_frame, text="已用: --", bg=DARK_THEME["bg"],
            fg=DARK_THEME["text_muted"], font=FONTS["mono_small"]
        )
        self.elapsed_label.pack(side="right", padx=20)

    def update_progress(self, task):
        """更新进度显示"""
        from utils.helpers import format_time_remaining, format_duration

        self.progress_bar["value"] = task.progress
        self.percent_label.config(text=f"{task.progress:.1f}%")

        if task.speed:
            self.speed_label.config(text=f"速度: {task.speed}")

        if task.elapsed_time > 0:
            self.elapsed_label.config(text=f"已用: {format_duration(task.elapsed_time)}")

        if task.remaining_time is not None:
            self.time_label.config(text=f"剩余: {format_time_remaining(task.remaining_time)}")

    def reset(self):
        """重置进度"""
        self.progress_bar["value"] = 0
        self.percent_label.config(text="0%")
        self.speed_label.config(text="速度: --")
        self.time_label.config(text="剩余: --")
        self.elapsed_label.config(text="已用: --")


class FileListWidget(tk.Frame):
    """文件列表控件"""

    def __init__(self, parent, on_remove=None, **kwargs):
        super().__init__(parent, bg=DARK_THEME["surface"], **kwargs)
        self._on_remove = on_remove
        self._items = {}
        self._setup_ui()

    def _setup_ui(self):
        # 标题栏
        header = tk.Frame(self, bg=DARK_THEME["surface"])
        header.pack(fill="x", padx=10, pady=(8, 4))

        tk.Label(
            header, text="📁 文件列表",
            bg=DARK_THEME["surface"], fg=DARK_THEME["text"],
            font=FONTS["heading"]
        ).pack(side="left")

        self.count_label = tk.Label(
            header, text="(0个文件)",
            bg=DARK_THEME["surface"], fg=DARK_THEME["text_muted"],
            font=FONTS["small"]
        )
        self.count_label.pack(side="left", padx=10)

        # 滚动区域
        container = tk.Frame(self, bg=DARK_THEME["surface"])
        container.pack(fill="both", expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(container, bg=DARK_THEME["surface"],
                                highlightthickness=0, height=150)
        scrollbar = ttk.Scrollbar(container, orient="vertical",
                                   command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=DARK_THEME["surface"])

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 空状态提示
        self.empty_label = tk.Label(
            self.scroll_frame,
            text="点击 [+ 添加文件] 或拖拽文件到此处",
            bg=DARK_THEME["surface"], fg=DARK_THEME["overlay"],
            font=FONTS["body"], pady=30
        )
        self.empty_label.pack(fill="x")

    def add_file(self, file_id: int, file_name: str, file_info: str):
        """添加文件到列表"""
        self.empty_label.pack_forget()

        item_frame = tk.Frame(self.scroll_frame, bg=DARK_THEME["surface2"])
        item_frame.pack(fill="x", padx=5, pady=2)

        # 序号
        tk.Label(
            item_frame, text=f"{file_id}",
            bg=DARK_THEME["surface2"], fg=DARK_THEME["accent"],
            font=FONTS["mono"], width=3
        ).pack(side="left", padx=(8, 4))

        # 文件名和信息
        text_frame = tk.Frame(item_frame, bg=DARK_THEME["surface2"])
        text_frame.pack(side="left", fill="x", expand=True)

        tk.Label(
            text_frame, text=file_name,
            bg=DARK_THEME["surface2"], fg=DARK_THEME["text"],
            font=FONTS["body"], anchor="w"
        ).pack(fill="x")

        tk.Label(
            text_frame, text=file_info,
            bg=DARK_THEME["surface2"], fg=DARK_THEME["text_muted"],
            font=FONTS["small"], anchor="w"
        ).pack(fill="x")

        # 状态
        status_label = tk.Label(
            item_frame, text="等待中",
            bg=DARK_THEME["surface2"], fg=DARK_THEME["warning"],
            font=FONTS["small"], width=8
        )
        status_label.pack(side="right", padx=5)

        # 删除按钮
        remove_btn = tk.Label(
            item_frame, text=" ✕ ",
            bg=DARK_THEME["surface2"], fg=DARK_THEME["error"],
            font=FONTS["body"], cursor="hand2"
        )
        remove_btn.pack(side="right", padx=5)
        remove_btn.bind("<Button-1>", lambda e, fid=file_id: self._remove_file(fid))

        self._items[file_id] = {
            "frame": item_frame,
            "status": status_label,
            "name": file_name,
        }
        self._update_count()

    def _remove_file(self, file_id):
        if file_id in self._items:
            self._items[file_id]["frame"].destroy()
            del self._items[file_id]
            self._update_count()
            if not self._items:
                self.empty_label.pack(fill="x")
            if self._on_remove:
                self._on_remove(file_id)

    def update_status(self, file_id: int, status: str, color: str = None):
        """更新文件状态"""
        if file_id in self._items:
            color = color or DARK_THEME["text_muted"]
            self._items[file_id]["status"].config(text=status, fg=color)

    def _update_count(self):
        self.count_label.config(text=f"({len(self._items)}个文件)")

    def clear(self):
        """清空列表"""
        for fid in list(self._items.keys()):
            self._items[fid]["frame"].destroy()
        self._items.clear()
        self._update_count()
        self.empty_label.pack(fill="x")

    def get_file_ids(self):
        return list(self._items.keys())
