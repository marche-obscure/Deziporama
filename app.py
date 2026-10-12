"""Deziporama: window of the ComfyUI workflow importer."""

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import ImageTk

import autostart
import i18n
import logo
import pixaroma
import shortcut
import single_instance
from i18n import t
from importer import ImportResult
from pixaroma_window import PixaromaWindow
from progress_window import ProgressWindow
from settings_dialog import SettingsDialog, valid_subfolder_name  # noqa: F401 (re-exported)
from tray import TITLE, TrayIcon
from ui import apply_app_icon, center_on_screen, set_app_id
from watcher import FolderWatcher

CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULTS = {
    "watch_dir": str(Path.home() / "Downloads"),
    "workflows_root": r"G:\GenerateurIA\ComfyUI\User\default\workflows",
    "subfolder": "",
    "process_existing": False,
    "desktop_shortcut_asked": False,
    "language": "",  # empty until the user has chosen one
    "pixaroma_dir": "",
    "pixaroma_subfolder": "",
    "pixaroma_check_at_start": False,
    "pixaroma_last_seen": 0,  # highest episode number already shown to the user
}
HEALTH_CHECK_MS = 2000
GEAR_COLOR = "#ff8a1f"  # logo orange: stands out on the dark banner


def load_config(path: Path = CONFIG_PATH) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    return {key: data[key] if type(data.get(key)) is type(default) else default
            for key, default in DEFAULTS.items()}


def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    # Write to a temporary file, then replace: a crash never loses the settings.
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def init_language(cfg: dict) -> None:
    """Saved language, or the Windows language until the user has chosen one."""
    i18n.set_language(cfg.get("language") or i18n.system_language())


def choice_dialog(parent, title: str, message: str, buttons: list[tuple[str, object]]):
    """Modal dialog with buttons; returns the value of the clicked button (None if closed)."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.resizable(False, False)
    # Attached to a hidden window, Windows would never show it (case of the second copy).
    if parent.winfo_viewable():
        dialog.transient(parent)
    dialog.attributes("-topmost", True)
    choice = {"value": None}

    def pick(value):
        choice["value"] = value
        dialog.destroy()

    body = ttk.Frame(dialog, padding=15)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=message, justify="center").pack(pady=(0, 12))
    row = ttk.Frame(body)
    row.pack()
    for label, value in buttons:
        ttk.Button(row, text=label, command=lambda v=value: pick(v)).pack(side="left", padx=3)
    dialog.protocol("WM_DELETE_WINDOW", lambda: pick(None))
    dialog.bind("<Escape>", lambda e: pick(None))
    center_on_screen(dialog)
    dialog.grab_set()
    parent.wait_window(dialog)
    return choice["value"]


def ask_already_running(parent) -> bool:
    """Warns about a second launch; True if the user wants to show the running copy."""
    return choice_dialog(
        parent, TITLE, t("already_running", title=TITLE),
        [(t("show_running"), True), (t("cancel"), False)]) is True


def is_login_start(argv: list[str]) -> bool:
    """True if the application was started by Windows at sign-in."""
    return any(flag in argv[1:] for flag in (autostart.STARTUP_FLAG, *autostart.LEGACY_FLAGS))


class App:
    def __init__(self, root: tk.Tk, at_login: bool = False) -> None:
        self.root = root
        self.cfg = load_config()
        init_language(self.cfg)
        self.results: queue.Queue = queue.Queue()
        self.commands: queue.Queue = queue.Queue()  # orders coming from the tray icon (other thread)
        self.messages: queue.Queue = queue.Queue()  # (text, tag) log lines coming from other threads
        self.pixaroma_window: PixaromaWindow | None = None
        self.progress_window: ProgressWindow | None = None
        self.watcher: FolderWatcher | None = None
        self._scheduled: dict[str, str] = {}
        self._translatable: list[tuple[object, str]] = []  # (widget, text key), see _retranslate
        self.tray = TrayIcon(on_show=lambda: self.commands.put("show"),
                             on_quit=lambda: self.commands.put("quit"),
                             on_pixaroma=lambda: self.commands.put("pixaroma"))
        self._stopped_in_settings = False
        self._settings_saved = False

        root.title(TITLE)
        root.minsize(640, 560)
        self.icon_images = self._set_window_icon()
        self.banner_label = self._build_banner()
        frame = ttk.Frame(root, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        # Folder settings live in the settings dialog (gear icon); these variables hold them.
        self.watch_var = tk.StringVar(value=self.cfg["watch_dir"])
        self.root_var = tk.StringVar(value=self.cfg["workflows_root"])
        self.sub_var = tk.StringVar(value=self.cfg["subfolder"] or t("root_label"))
        self.pixaroma_var = tk.StringVar(value=self.cfg["pixaroma_dir"])
        self.pixaroma_sub_var = tk.StringVar(value=self.cfg["pixaroma_subfolder"] or t("root_label"))
        self.existing_var = tk.BooleanVar(value=self.cfg["process_existing"])
        self.pixaroma_check_var = tk.BooleanVar(value=self.cfg["pixaroma_check_at_start"])

        self.dest_label = ttk.Label(frame)
        self.dest_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 2))
        self.pixaroma_label = ttk.Label(frame)
        self.pixaroma_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self._tr(ttk.Checkbutton(frame, variable=self.existing_var), "process_existing").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=3)
        try:
            enabled = autostart.is_enabled()
            if enabled:
                autostart.enable()  # rewrites the Run entry with the current command (e.g. after an update)
        except OSError:
            enabled = False
        self.autostart_var = tk.BooleanVar(value=enabled)
        self._tr(ttk.Checkbutton(frame, variable=self.autostart_var), "autostart").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=3)
        self.autostart_var.trace_add("write", lambda *_: self._apply_autostart())
        self._tr(ttk.Checkbutton(frame, variable=self.pixaroma_check_var), "pixaroma_check_at_start").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=3)

        buttons = ttk.Frame(frame)
        # Shown only when watching was stopped to change folders and not restarted (see _open_settings).
        self.stop_notice = ttk.Label(frame, foreground="#b35900")
        self.stop_notice.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.stop_notice.grid_remove()

        buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=6)
        buttons.columnconfigure(0, weight=1)
        self.toggle_btn = ttk.Button(buttons, command=self._toggle)
        self.toggle_btn.grid(row=0, column=0, sticky="ew")
        self.retry_btn = self._tr(ttk.Button(buttons, command=self._retry, state="disabled"), "retry")
        self.retry_btn.grid(row=0, column=1, padx=(5, 0))
        self.shortcut_btn = self._tr(ttk.Button(buttons, command=self._create_shortcut), "create_shortcut")
        self.shortcut_btn.grid(row=0, column=2, padx=(5, 0))
        self.pixaroma_btn = self._tr(ttk.Button(buttons, command=self._open_pixaroma), "pixaroma_button")
        self.pixaroma_btn.grid(row=0, column=3, padx=(5, 0))

        self.log = tk.Text(frame, height=14, state="disabled", wrap="word")
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(7, weight=1)
        self.log.tag_configure("ok", foreground="#1a7f37")
        self.log.tag_configure("ignored", foreground="#777777")
        self.log.tag_configure("error", foreground="#cf222e")
        self.log.tag_configure("warn", foreground="#b35900")

        for var in (self.watch_var, self.root_var, self.sub_var, self.pixaroma_var, self.pixaroma_sub_var,
                    self.existing_var, self.pixaroma_check_var):
            var.trace_add("write", lambda *_: self._save())
        self._update_summary()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.bind("<Unmap>", self._on_unmap)
        self._schedule(200, self._drain)
        self._schedule(HEALTH_CHECK_MS, self._check_health)
        self._set_running(False)
        self._update_shortcut_button()
        if self.cfg["pixaroma_check_at_start"]:
            self._check_pixaroma_news()
        if at_login:
            self._hide_to_tray()
            self._toggle()
        elif not self.cfg["language"] or self._should_offer_shortcut():
            self._schedule(300, self._first_launch_questions)

    # --- Building -------------------------------------------------------------

    def _tr(self, widget, key: str):
        """Gives `widget` the text `key` and keeps it translated when the language changes."""
        widget.configure(text=t(key))
        self._translatable.append((widget, key))
        return widget

    def _set_window_icon(self) -> list:
        """Title bar and taskbar icon, also the default for dialogs (images kept referenced)."""
        return apply_app_icon(self.root, logo.ICO_PATH)

    def _build_banner(self):
        """Dark banner with the logo (if its file exists) and the language selector."""
        band = tk.Frame(self.root, background=logo.BANNER_BACKGROUND)
        band.pack(fill="x")
        label = None
        img = logo.banner_image(420)
        if img is not None:
            self._banner_photo = ImageTk.PhotoImage(img, master=self.root)
            label = tk.Label(band, image=self._banner_photo, background=logo.BANNER_BACKGROUND, borderwidth=0)
            label.pack()
        else:
            tk.Frame(band, height=40, background=logo.BANNER_BACKGROUND).pack()
        self._build_language_selector(band)
        return label

    def _build_language_selector(self, band) -> None:
        """Top-right corner of the banner: settings (gear) and language selector."""
        colors = dict(background="#2b2a31", foreground="white", activebackground="#3d3c45",
                      activeforeground="white")
        corner = tk.Frame(band, background=logo.BANNER_BACKGROUND)
        corner.place(relx=1.0, x=-10, y=10, anchor="ne")
        self.settings_btn = tk.Button(corner, text="⚙", command=self._open_settings,
                                      font=("Segoe UI Symbol", 14, "bold"), highlightthickness=0, borderwidth=0,
                                      relief="flat", cursor="hand2", padx=6, pady=0,
                                      **dict(colors, foreground=GEAR_COLOR, activeforeground=GEAR_COLOR))
        self.settings_btn.pack(side="left", padx=(0, 6))
        self.language_menu_values = list(i18n.LANGUAGES.values())
        self.language_var = tk.StringVar(value=i18n.LANGUAGES[i18n.get_language()])
        menu = tk.OptionMenu(corner, self.language_var, *self.language_menu_values)
        menu.configure(highlightthickness=0, borderwidth=0, relief="flat", cursor="hand2", **colors)
        menu["menu"].configure(**colors)
        menu.pack(side="left")
        self.language_var.trace_add("write", lambda *_: self._on_language_selected())

    # --- Languages ------------------------------------------------------------

    def _on_language_selected(self) -> None:
        names = {name: code for code, name in i18n.LANGUAGES.items()}
        code = names.get(self.language_var.get())
        if code and (code != i18n.get_language() or code != self.cfg["language"]):
            self._apply_language(code)

    def _apply_language(self, code: str) -> None:
        """Switches the whole interface to `code` and remembers the choice."""
        i18n.set_language(code)
        self.cfg["language"] = i18n.get_language()
        if self.language_var.get() != i18n.LANGUAGES[i18n.get_language()]:
            self.language_var.set(i18n.LANGUAGES[i18n.get_language()])
        self._retranslate()
        self._save()

    def _retranslate(self) -> None:
        for widget, key in self._translatable:
            widget.configure(text=t(key))
        self.stop_notice.configure(text=t("stop_notice"))
        for var in (self.sub_var, self.pixaroma_sub_var):
            if var.get() in i18n.root_labels():
                var.set(t("root_label"))
        self._update_summary()
        self._set_running(bool(self.watcher and self.watcher.running))
        self.tray.refresh_menu()

    def _ask_language(self) -> None:
        """First launch: the Windows language comes first; closing the dialog keeps it."""
        system = i18n.system_language()
        codes = [system, *(code for code in i18n.LANGUAGES if code != system)]
        choice = choice_dialog(self.root, TITLE, i18n.LANGUAGE_PROMPT,
                               [(i18n.LANGUAGES[code], code) for code in codes])
        self._apply_language(choice or system)

    def _first_launch_questions(self) -> None:
        """Asked once each: the language, then the desktop shortcut (in the chosen language)."""
        if not self.cfg["language"]:
            self._ask_language()
        if self._should_offer_shortcut():
            self._offer_shortcut()

    # --- Pixaroma -------------------------------------------------------------

    def _run_background(self, fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _open_pixaroma(self) -> None:
        if not self.pixaroma_var.get():
            self._write(t("log_pixaroma_folder_missing"), "error")
            return
        if self.pixaroma_window and self.pixaroma_window.window.winfo_exists():
            self.pixaroma_window.window.deiconify()
            self.pixaroma_window.window.lift()
            return
        self.pixaroma_window = PixaromaWindow(
            self.root, self._pixaroma_dest(), self.cfg["pixaroma_last_seen"],
            scan_dir=Path(self.pixaroma_var.get()),
            on_message=lambda text, tag: self.messages.put((text, tag)),
            on_result=self.results.put,
            on_seen=self._pixaroma_seen)

    def _pixaroma_seen(self, newest: int) -> None:
        """The list was shown: episodes up to `newest` are no longer "new" next time."""
        if newest > self.cfg["pixaroma_last_seen"]:
            self.cfg["pixaroma_last_seen"] = newest
            self._save()

    # Tray "Pixaroma" command: check, then download the new episodes without opening the window.

    def _tell(self, text: str, tag: str) -> None:
        """Message in the log and in a centered dialog with OK: unlike a Windows notification,
        it cannot be missed or hidden by "Do not disturb" (the main window may be hidden)."""
        self._write(text, tag)
        choice_dialog(self.root, TITLE, text, [(t("ok"), True)])

    def _tray_pixaroma(self) -> None:
        if not self.pixaroma_var.get():
            self._tell(t("log_pixaroma_folder_missing"), "error")
            return

        def work():
            try:
                self.commands.put(("pixaroma_found", pixaroma.fetch_episodes()))
            except pixaroma.PixaromaError as e:
                self.commands.put(("pixaroma_failed", t("pixaroma_list_failed", error=e)))

        self._run_background(work)

    def _offer_new_episodes(self, episodes: list) -> None:
        imported = pixaroma.imported_numbers(Path(self.pixaroma_var.get()))
        new = [ep for ep in episodes
               if ep.number > self.cfg["pixaroma_last_seen"] and ep.number not in imported]
        if not new:
            self._tell(t("log_pixaroma_up_to_date"), "ignored")
            return
        names = "\n".join(ep.folder_name for ep in new)
        if choice_dialog(self.root, TITLE, t("pixaroma_new_question", count=len(new), names=names),
                         [(t("download"), True), (t("later"), False)]) is not True:
            return  # still "new" next time
        dest = self._pixaroma_dest()
        self.progress_window = ProgressWindow(self.root)

        def work():
            available, failed = [], 0
            for index, ep in enumerate(new, 1):
                self.messages.put((t("log_pixaroma_downloading", name=ep.zip_name), "ignored"))
                last = {}

                def progress(phase, done, total, ep=ep, index=index, last=last):
                    # Only whole-percent changes go to the Tk thread.
                    percent = done * 100 // total if total else 0
                    if last.get(phase) != percent:
                        last[phase] = percent
                        self.commands.put(("pixaroma_progress", ep.folder_name, index, len(new),
                                           phase, done, total))

                result = pixaroma.import_episode(ep, dest, progress=progress)
                self.results.put(result)
                if result.status == "imported":
                    available.append(result.target.name)
                else:
                    failed += 1
            self.commands.put(("pixaroma_done", available, failed, max(ep.number for ep in new)))

        self._run_background(work)

    def _pixaroma_downloaded(self, available: list, failed: int, newest: int) -> None:
        """Download, extraction and renaming are finished: close the progress window and report."""
        if self.progress_window:
            self.progress_window.close()
            self.progress_window = None
        self._pixaroma_seen(newest)
        parts = []
        if available:
            parts.append(t("pixaroma_available", names="\n".join(available)))
        if failed:
            parts.append(t("pixaroma_some_failed", count=failed))
        self._tell("\n\n".join(parts), "warn" if failed else "ok")

    def _check_pixaroma_news(self) -> None:
        last_seen = self.cfg["pixaroma_last_seen"]

        def work():
            try:
                episodes = pixaroma.fetch_episodes()
            except pixaroma.PixaromaError as e:
                self.messages.put((t("pixaroma_list_failed", error=e), "warn"))
                return
            new = [ep.number for ep in episodes if ep.number > last_seen]
            if new:
                self.messages.put((t("log_pixaroma_new", count=len(new),
                                     numbers=", ".join(map(str, new))), "ok"))
            else:
                self.messages.put((t("log_pixaroma_up_to_date"), "ignored"))

        self._run_background(work)

    # --- Settings -------------------------------------------------------------

    def _open_settings(self) -> None:
        values = {"watch_dir": self.watch_var.get(), "workflows_root": self.root_var.get(),
                  "subfolder": self.cfg["subfolder"], "pixaroma_dir": self.pixaroma_var.get(),
                  "pixaroma_subfolder": self.cfg["pixaroma_subfolder"]}
        running = bool(self.watcher and self.watcher.running)
        folders_before = (self.watch_var.get(), self.root_var.get())
        self._stopped_in_settings = self._settings_saved = False
        SettingsDialog(self.root, values, running, self._save_from_settings,
                       on_stop=self._stop_from_settings).run_modal()
        if self._stopped_in_settings and self._settings_saved:
            folders_changed = folders_before != (self.watch_var.get(), self.root_var.get())
            if self._ask_restart():
                self._toggle()
            elif folders_changed:
                self.stop_notice.configure(text=t("stop_notice"))
                self.stop_notice.grid()

    def _save_from_settings(self, values: dict) -> None:
        self._settings_saved = True
        self._apply_settings(values)

    def _stop_from_settings(self) -> None:
        self._stopped_in_settings = True
        self._stop_watching()

    def _ask_restart(self) -> bool:
        return choice_dialog(self.root, TITLE, t("restart_question"),
                             [(t("restart"), True), (t("not_now"), False)]) is True

    def _stop_watching(self) -> None:
        if self.watcher and self.watcher.running:
            self._toggle()

    def _apply_settings(self, values: dict) -> None:
        self.watch_var.set(values["watch_dir"])
        self.root_var.set(values["workflows_root"])
        self.sub_var.set(values["subfolder"] or t("root_label"))
        self.pixaroma_var.set(values["pixaroma_dir"])
        self.pixaroma_sub_var.set(values.get("pixaroma_subfolder") or t("root_label"))
        self._update_summary()

    def _pixaroma_dest(self) -> Path:
        """Pixaroma folder, plus its subfolder unless "(root)" is chosen."""
        base = Path(self.pixaroma_var.get())
        sub = self.pixaroma_sub_var.get()
        return base if sub in i18n.root_labels() or not sub else base / sub

    def _update_summary(self) -> None:
        self.dest_label.configure(text=t("destination_summary", path=self._dest()))
        pixaroma_path = self._pixaroma_dest() if self.pixaroma_var.get() else "—"
        self.pixaroma_label.configure(text=t("pixaroma_summary", path=pixaroma_path))

    def _dest(self) -> Path:
        # Called from the watcher thread: only reads the config, never Tkinter.
        cfg = self.cfg
        root = Path(cfg["workflows_root"])
        return root / cfg["subfolder"] if cfg["subfolder"] else root

    # --- Watching -------------------------------------------------------------

    def _toggle(self) -> None:
        if self.watcher and self.watcher.running:
            self.watcher.stop()
            self._set_running(False)
            self._write(t("log_stopped"), "ignored")
            return
        watch_dir, root = Path(self.watch_var.get()), Path(self.root_var.get())
        if not watch_dir.is_dir():
            self._write(t("log_watch_missing", path=watch_dir), "error")
            return
        if not root.is_dir():
            self._write(t("log_root_missing", path=root), "error")
            return
        self.watcher = FolderWatcher(watch_dir, self._dest, self.results.put)
        try:
            self.watcher.start(process_existing=self.existing_var.get())
        except OSError as e:
            self._write(t("log_cannot_watch", path=watch_dir, error=e), "error")
            return
        self._set_running(True)
        self.stop_notice.grid_remove()
        self._write(t("log_watching", path=watch_dir), "ignored")

    def _retry(self) -> None:
        if self.watcher and self.watcher.running and self.watcher.failed_count:
            self._write(t("log_retrying", count=self.watcher.failed_count), "ignored")
            self.watcher.retry_failed()
        self._update_retry()

    def _update_retry(self) -> None:
        active = bool(self.watcher and self.watcher.running and self.watcher.failed_count)
        self.retry_btn.configure(state="normal" if active else "disabled")

    def _check_health(self) -> None:
        if self.watcher and self.watcher.running and not self.watcher.healthy:
            self.watcher.stop()
            self._set_running(False)
            self._write(t("log_interrupted", path=self.watcher.watch_dir), "error")
        self._schedule(HEALTH_CHECK_MS, self._check_health)

    # --- Desktop shortcut -----------------------------------------------------

    def _shortcut_exists(self) -> bool:
        try:
            return shortcut.exists()
        except OSError:
            return False

    def _should_offer_shortcut(self) -> bool:
        return not self.cfg["desktop_shortcut_asked"] and not self._shortcut_exists()

    def _update_shortcut_button(self) -> None:
        self.shortcut_btn.configure(state="disabled" if self._shortcut_exists() else "normal")

    def _create_shortcut(self) -> None:
        try:
            path = shortcut.create()
        except OSError as e:
            self._write(t("log_shortcut_failed", error=e), "error")
        else:
            self._write(t("log_shortcut_created", path=path), "ok")
        self._update_shortcut_button()

    def _offer_shortcut(self) -> None:
        """First launch: offers the desktop shortcut, only once whatever the answer."""
        self.cfg["desktop_shortcut_asked"] = True
        self._save()
        if choice_dialog(self.root, TITLE, t("offer_shortcut", title=TITLE),
                         [(t("yes_create"), True), (t("no_thanks"), False)]) is True:
            self._create_shortcut()

    def _set_running(self, running: bool) -> None:
        self.toggle_btn.configure(text=t("stop") if running else t("start"))
        self.tray.set_tooltip(t("tooltip_active" if running else "tooltip_stopped", title=TITLE))
        self._update_retry()

    def _drain(self) -> None:
        while True:
            try:
                command = self.commands.get_nowait()
            except queue.Empty:
                break
            if command == "show":
                self._show_window()
            elif command == "quit":
                self._quit()
                return
            elif command == "pixaroma":
                self._tray_pixaroma()
            elif command[0] == "pixaroma_found":
                self._offer_new_episodes(command[1])
            elif command[0] == "pixaroma_progress":
                if self.progress_window:
                    self.progress_window.update(*command[1:])
            elif command[0] == "pixaroma_done":
                self._pixaroma_downloaded(*command[1:])
            elif command[0] == "pixaroma_failed":
                self._tell(command[1], "warn")
        while True:
            try:
                text, tag = self.messages.get_nowait()
            except queue.Empty:
                break
            self._write(text, tag)
        while True:
            try:
                result: ImportResult = self.results.get_nowait()
            except queue.Empty:
                break
            name = result.source.name
            if result.status == "imported":
                self._write(t("log_imported", name=name, target=result.target), "ok")
                if result.message:
                    self._write(t("log_warning", message=result.message), "warn")
            elif result.status == "ignored":
                self._write(t("log_ignored", name=name), "ignored")
            else:
                self._write(t("log_error", name=name, message=result.message), "error")
        self._update_retry()
        self._schedule(200, self._drain)

    # --- Misc -----------------------------------------------------------------

    def _write(self, message: str, tag: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {message}\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _save(self) -> None:
        sub = self.sub_var.get()
        self.cfg = {
            "watch_dir": self.watch_var.get(),
            "workflows_root": self.root_var.get(),
            "subfolder": "" if sub in i18n.root_labels() else sub,
            "process_existing": self.existing_var.get(),
            "desktop_shortcut_asked": self.cfg.get("desktop_shortcut_asked", False),
            "language": self.cfg.get("language", ""),
            "pixaroma_dir": self.pixaroma_var.get(),
            "pixaroma_subfolder": "" if self.pixaroma_sub_var.get() in i18n.root_labels()
            else self.pixaroma_sub_var.get(),
            "pixaroma_check_at_start": self.pixaroma_check_var.get(),
            "pixaroma_last_seen": self.cfg.get("pixaroma_last_seen", 0),
        }
        self._update_summary()
        try:
            save_config(self.cfg)
        except OSError as e:
            self._write(t("log_settings_not_saved", error=e), "error")

    def _apply_autostart(self) -> None:
        wanted = self.autostart_var.get()
        try:
            autostart.enable() if wanted else autostart.disable()
        except OSError as e:
            self._write(t("log_autostart_failed", error=e), "error")
            if self.autostart_var.get() != (not wanted):
                self.autostart_var.set(not wanted)

    # --- Notification area and closing ----------------------------------------

    def _on_unmap(self, event) -> None:
        # Minimize button: the window leaves the taskbar for the notification area.
        if event.widget is self.root and self.root.state() == "iconic":
            self._hide_to_tray()

    def _hide_to_tray(self) -> None:
        self.root.withdraw()
        self.tray.show()

    def _show_window(self) -> None:
        self._update_shortcut_button()  # the shortcut may have been created or deleted meanwhile
        self.tray.hide()
        self.root.deiconify()
        self.root.lift()
        # When recalled by another copy, Windows would leave the window behind the others.
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def _ask_close(self) -> str | None:
        """"Minimize / Quit / Cancel" dialog. Returns "minimize", "quit" or None."""
        return choice_dialog(
            self.root, t("close_title"), t("close_message", title=TITLE),
            [(t("minimize_to_tray"), "minimize"), (t("quit"), "quit"), (t("cancel"), None)])

    def _close(self) -> None:
        choice = self._ask_close()
        if choice == "minimize":
            self._hide_to_tray()
        elif choice == "quit":
            self._quit()

    def _schedule(self, ms: int, callback) -> None:
        """root.after remembered per function, so that everything can be cancelled on quit."""
        self._scheduled[callback.__name__] = self.root.after(ms, callback)

    def _quit(self) -> None:
        for after_id in self._scheduled.values():
            self.root.after_cancel(after_id)
        self._scheduled.clear()
        if self.watcher:
            self.watcher.stop()
        self.tray.stop()
        self.root.destroy()


def main() -> None:
    at_login = is_login_start(sys.argv)
    set_app_id()
    init_language(load_config())
    instance = single_instance.SingleInstance()
    if not instance.acquire():
        # Already running: at sign-in, leave silently; otherwise ask.
        if not at_login:
            root = tk.Tk()
            root.withdraw()
            icons = apply_app_icon(root, logo.ICO_PATH)  # noqa: F841 (kept referenced)
            if ask_already_running(root):
                single_instance.signal_show()
            root.destroy()
        instance.close()
        return
    root = tk.Tk()
    app = App(root, at_login=at_login)
    listener = single_instance.listen_show(single_instance.INSTANCE_NAME,
                                           lambda: app.commands.put("show"))
    try:
        root.mainloop()
    finally:
        listener.stop()
        instance.close()


if __name__ == "__main__":
    main()
