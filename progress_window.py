"""Small window following the download and extraction of Pixaroma episodes."""

import tkinter as tk
from tkinter import ttk

from i18n import t
from tray import TITLE
from ui import center_on_screen

PHASE_KEYS = {"download": "progress_downloading", "extract": "progress_extracting"}


class ProgressWindow:
    def __init__(self, parent) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title(TITLE)
        self.window.resizable(False, False)
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", lambda: None)  # closes by itself when done
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill="both", expand=True)
        self.episode_label = ttk.Label(frame, font=("Segoe UI", 10, "bold"))
        self.episode_label.pack(anchor="w")
        self.phase_label = ttk.Label(frame, text=t("progress_downloading"))
        self.phase_label.pack(anchor="w", pady=(6, 4))
        self.bar = ttk.Progressbar(frame, length=420, maximum=100, mode="determinate")
        self.bar.pack(fill="x")
        self.percent_label = ttk.Label(frame, text="0 %")
        self.percent_label.pack(anchor="e", pady=(4, 0))
        center_on_screen(self.window)

    def update(self, name: str, index: int, count: int, phase: str, done: int, total: int) -> None:
        percent = min(100, done * 100 // total) if total else 0
        self.episode_label.configure(text=f"{name} ({index}/{count})")
        self.phase_label.configure(text=t(PHASE_KEYS.get(phase, "progress_downloading")))
        self.bar["value"] = percent
        self.percent_label.configure(text=f"{percent} %")

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
