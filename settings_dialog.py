"""Settings window (gear icon): watched folder, workflows folder and subfolder, Pixaroma folder."""

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

import i18n
from i18n import t
from ui import center_on_screen

NOTICE_BACKGROUND = "#fff1e0"
NOTICE_FOREGROUND = "#8a4500"
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def valid_subfolder_name(name: str) -> bool:
    """A single folder level, inside the workflows root, with a name Windows accepts."""
    name = name.strip()
    return bool(name) and not name.startswith(".") and not _FORBIDDEN.search(name)


class SettingsDialog:
    """Edits a copy of the folder settings; `on_save` receives them only when OK is clicked."""

    def __init__(self, parent, values: dict, running: bool, on_save: Callable[[dict], None],
                 on_stop: Callable[[], None] | None = None) -> None:
        self._values = dict(values)
        self._on_save = on_save
        self._on_stop = on_stop
        self.window = tk.Toplevel(parent)
        self.window.title(t("settings_title"))
        self.window.resizable(True, False)
        if parent.winfo_viewable():
            self.window.transient(parent)

        self.running_notice = self._build_running_notice() if running else None
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1, minsize=380)

        self.watch_var = tk.StringVar(value=values["watch_dir"])
        self.root_var = tk.StringVar(value=values["workflows_root"])
        self.sub_var = tk.StringVar(value=values["subfolder"] or t("root_label"))
        self.pixaroma_var = tk.StringVar(value=values["pixaroma_dir"])
        self.pixaroma_sub_var = tk.StringVar(value=values.get("pixaroma_subfolder") or t("root_label"))

        self.watch_entry, self.watch_btn = self._folder_row(frame, 0, "watched_folder", self.watch_var)
        self.root_entry, self.root_btn = self._folder_row(frame, 1, "workflows_folder", self.root_var)
        self.sub_combo = self._subfolder_row(frame, 2, "subfolder", self.sub_var, pixaroma=False)
        ttk.Separator(frame).grid(row=3, column=0, columnspan=3, sticky="ew", pady=8)
        self.pixaroma_entry, self.pixaroma_btn = self._folder_row(frame, 4, "pixaroma_folder", self.pixaroma_var)
        self.pixaroma_sub_combo = self._subfolder_row(frame, 5, "pixaroma_subfolder",
                                                      self.pixaroma_sub_var, pixaroma=True)

        if running:  # the watcher uses these two folders: they cannot change while it runs
            self._lock_watched_folders(True)

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text=t("ok"), command=self.ok).pack(side="left", padx=3)
        ttk.Button(buttons, text=t("cancel"), command=self.cancel).pack(side="left", padx=3)

        self.root_var.trace_add("write", lambda *_: self._refresh_subfolders())
        self.pixaroma_var.trace_add("write", lambda *_: self._refresh_subfolders())
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

    def _subfolder_row(self, frame, row, key, var, pixaroma: bool):
        ttk.Label(frame, text=t(key)).grid(row=row, column=0, sticky="w", pady=3)
        combo = ttk.Combobox(frame, textvariable=var, state="readonly", postcommand=self._refresh_subfolders)
        combo.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text=t("new"), command=lambda: self._ask_new_subfolder(pixaroma)).grid(
            row=row, column=2, padx=(5, 0))
        return combo

    @staticmethod
    def _choices(folder: str) -> list[str]:
        try:
            names = sorted((p.name for p in Path(folder).iterdir()
                            if p.is_dir() and not p.name.startswith(".")), key=str.lower)
        except OSError:
            names = []
        return [t("root_label"), *names]

    def subfolder_choices(self) -> list[str]:
        return self._choices(self.root_var.get())

    def pixaroma_subfolder_choices(self) -> list[str]:
        return self._choices(self.pixaroma_var.get()) if self.pixaroma_var.get() else [t("root_label")]

    def _refresh_subfolders(self) -> None:
        self.sub_combo["values"] = self.subfolder_choices()
        self.pixaroma_sub_combo["values"] = self.pixaroma_subfolder_choices()

    def create_subfolder(self, name: str, pixaroma: bool = False) -> str | None:
        """Creates and selects a subfolder of the workflows folder (or of the Pixaroma folder);
        returns an error message, or None on success."""
        if not valid_subfolder_name(name):
            return t("invalid_name_message")
        name = name.strip()
        base, var = (self.pixaroma_var, self.pixaroma_sub_var) if pixaroma else (self.root_var, self.sub_var)
        if not base.get():
            return t("cannot_create_folder", error=t("pixaroma_folder"))
        try:
            (Path(base.get()) / name).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return t("cannot_create_folder", error=e)
        self._refresh_subfolders()
        var.set(name)
        return None

    def _ask_new_subfolder(self, pixaroma: bool) -> None:
        name = simpledialog.askstring(t("new_subfolder_title"), t("new_subfolder_prompt"), parent=self.window)
        if name is None:
            return
        error = self.create_subfolder(name, pixaroma)
        if error:
            messagebox.showerror(t("error_title"), error, parent=self.window)

    # --- Closing --------------------------------------------------------------

    def ok(self) -> None:
        def subfolder(var):
            return "" if var.get() in i18n.root_labels() else var.get()

        self._on_save(dict(self._values,
                           watch_dir=self.watch_var.get(),
                           workflows_root=self.root_var.get(),
                           subfolder=subfolder(self.sub_var),
                           pixaroma_dir=self.pixaroma_var.get(),
                           pixaroma_subfolder=subfolder(self.pixaroma_sub_var)))
        self.window.destroy()

    # --- Watching running -----------------------------------------------------

    def _build_running_notice(self):
        """Orange band explaining why two folders are locked, with a button to stop watching."""
        band = tk.Frame(self.window, background=NOTICE_BACKGROUND, padx=12, pady=8)
        band.pack(fill="x")
        self.running_notice_label = tk.Label(band, text=t("settings_running_notice"), background=NOTICE_BACKGROUND,
                                             foreground=NOTICE_FOREGROUND, justify="left", anchor="w")
        self.running_notice_label.pack(side="left", fill="x", expand=True)
        self.stop_btn = ttk.Button(band, text=t("stop_watching"), command=self.stop_watching)
        self.stop_btn.pack(side="right", padx=(10, 0))
        return band

    def _lock_watched_folders(self, locked: bool) -> None:
        for widget in (self.watch_entry, self.watch_btn, self.root_entry, self.root_btn):
            widget.configure(state="disabled" if locked else "normal")

    def stop_watching(self) -> None:
        """Stops watching without leaving the dialog, then unlocks the folders."""
        if self._on_stop:
            self._on_stop()
        self._lock_watched_folders(False)
        if self.running_notice is not None:
            self.running_notice.destroy()

    def cancel(self) -> None:
        self.window.destroy()

    def run_modal(self) -> None:
        self.window.grab_set()
        self.window.wait_window()
