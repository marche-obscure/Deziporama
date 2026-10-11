"""Settings window (gear icon): watched folder, workflows folder and subfolder, Pixaroma folder."""

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

import i18n
from i18n import t
from ui import center_on_screen

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def valid_subfolder_name(name: str) -> bool:
    """A single folder level, inside the workflows root, with a name Windows accepts."""
    name = name.strip()
    return bool(name) and not name.startswith(".") and not _FORBIDDEN.search(name)


class SettingsDialog:
    """Edits a copy of the folder settings; `on_save` receives them only when OK is clicked."""

    def __init__(self, parent, values: dict, running: bool, on_save: Callable[[dict], None]) -> None:
        self._values = dict(values)
        self._on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.title(t("settings_title"))
        self.window.resizable(True, False)
        if parent.winfo_viewable():
            self.window.transient(parent)

        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1, minsize=380)

        self.watch_var = tk.StringVar(value=values["watch_dir"])
        self.root_var = tk.StringVar(value=values["workflows_root"])
        self.sub_var = tk.StringVar(value=values["subfolder"] or t("root_label"))
        self.pixaroma_var = tk.StringVar(value=values["pixaroma_dir"])

        self.watch_entry, self.watch_btn = self._folder_row(frame, 0, "watched_folder", self.watch_var)
        self.root_entry, self.root_btn = self._folder_row(frame, 1, "workflows_folder", self.root_var)
        ttk.Label(frame, text=t("subfolder")).grid(row=2, column=0, sticky="w", pady=3)
        self.sub_combo = ttk.Combobox(frame, textvariable=self.sub_var, state="readonly",
                                      postcommand=self._refresh_subfolders)
        self.sub_combo.grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text=t("new"), command=self._ask_new_subfolder).grid(row=2, column=2, padx=(5, 0))
        self.pixaroma_entry, self.pixaroma_btn = self._folder_row(frame, 3, "pixaroma_folder", self.pixaroma_var)

        if running:  # the watcher uses these two folders: they cannot change while it runs
            for widget in (self.watch_entry, self.watch_btn, self.root_entry, self.root_btn):
                widget.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text=t("ok"), command=self.ok).pack(side="left", padx=3)
        ttk.Button(buttons, text=t("cancel"), command=self.cancel).pack(side="left", padx=3)

        self.root_var.trace_add("write", lambda *_: self._refresh_subfolders())
        self._refresh_subfolders()
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.bind("<Escape>", lambda e: self.cancel())
        center_on_screen(self.window)

    def _folder_row(self, frame, row, key, var):
        ttk.Label(frame, text=t(key)).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(frame, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=3)

        def browse():
            chosen = filedialog.askdirectory(parent=self.window, initialdir=var.get() or None)
            if chosen:
                var.set(str(Path(chosen)))

        button = ttk.Button(frame, text=t("browse"), command=browse)
        button.grid(row=row, column=2, padx=(5, 0))
        return entry, button

    # --- Subfolders -----------------------------------------------------------

    def subfolder_choices(self) -> list[str]:
        root = Path(self.root_var.get())
        try:
            names = sorted((p.name for p in root.iterdir()
                            if p.is_dir() and not p.name.startswith(".")), key=str.lower)
        except OSError:
            names = []
        return [t("root_label"), *names]

    def _refresh_subfolders(self) -> None:
        self.sub_combo["values"] = self.subfolder_choices()

    def create_subfolder(self, name: str) -> str | None:
        """Creates and selects the subfolder; returns an error message, or None on success."""
        if not valid_subfolder_name(name):
            return t("invalid_name_message")
        name = name.strip()
        try:
            (Path(self.root_var.get()) / name).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return t("cannot_create_folder", error=e)
        self._refresh_subfolders()
        self.sub_var.set(name)
        return None

    def _ask_new_subfolder(self) -> None:
        name = simpledialog.askstring(t("new_subfolder_title"), t("new_subfolder_prompt"), parent=self.window)
        if name is None:
            return
        error = self.create_subfolder(name)
        if error:
            messagebox.showerror(t("error_title"), error, parent=self.window)

    # --- Closing --------------------------------------------------------------

    def ok(self) -> None:
        sub = self.sub_var.get()
        self._on_save(dict(self._values,
                           watch_dir=self.watch_var.get(),
                           workflows_root=self.root_var.get(),
                           subfolder="" if sub in i18n.root_labels() else sub,
                           pixaroma_dir=self.pixaroma_var.get()))
        self.window.destroy()

    def cancel(self) -> None:
        self.window.destroy()

    def run_modal(self) -> None:
        self.window.grab_set()
        self.window.wait_window()
