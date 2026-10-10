"""Deziporama: window of the ComfyUI workflow importer."""

import json
import os
import queue
import re
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import ImageTk

import autostart
import logo
import shortcut
import single_instance
from importer import ImportResult
from tray import TITLE, TrayIcon
from watcher import FolderWatcher

CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULTS = {
    "watch_dir": str(Path.home() / "Downloads"),
    "workflows_root": r"G:\GenerateurIA\ComfyUI\User\default\workflows",
    "subfolder": "",
    "process_existing": False,
    "desktop_shortcut_asked": False,
}
ROOT_LABEL = "(root)"
HEALTH_CHECK_MS = 2000
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def valid_subfolder_name(name: str) -> bool:
    """A single folder level, inside the workflows root, with a name Windows accepts."""
    name = name.strip()
    return bool(name) and not name.startswith(".") and not _FORBIDDEN.search(name)


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


def center_on_screen(window) -> None:
    """Centers the window on the screen (Tk would put it in the top-left corner)."""
    window.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 2
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")


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
    ttk.Label(body, text=message).pack(pady=(0, 12))
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
        parent, TITLE,
        f"{TITLE} is already running\n"
        "(its icon is in the notification area, next to the clock).\n\n"
        "Do you want to show its window?",
        [("Show the running one", True), ("Cancel", False)]) is True


def is_login_start(argv: list[str]) -> bool:
    """True if the application was started by Windows at sign-in."""
    return any(flag in argv[1:] for flag in (autostart.STARTUP_FLAG, *autostart.LEGACY_FLAGS))


class App:
    def __init__(self, root: tk.Tk, at_login: bool = False) -> None:
        self.root = root
        self.cfg = load_config()
        self.results: queue.Queue = queue.Queue()
        self.commands: queue.Queue = queue.Queue()  # orders coming from the tray icon (other thread)
        self.watcher: FolderWatcher | None = None
        self._scheduled: dict[str, str] = {}
        self.tray = TrayIcon(on_show=lambda: self.commands.put("show"),
                             on_quit=lambda: self.commands.put("quit"))

        root.title(TITLE)
        root.minsize(640, 560)
        self.icon_images = self._set_window_icon()
        self.banner_label = self._build_banner()
        frame = ttk.Frame(root, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self.watch_var = tk.StringVar(value=self.cfg["watch_dir"])
        self.root_var = tk.StringVar(value=self.cfg["workflows_root"])
        self.sub_var = tk.StringVar(value=self.cfg["subfolder"] or ROOT_LABEL)
        self.existing_var = tk.BooleanVar(value=self.cfg["process_existing"])

        self.watch_entry, self.watch_btn = self._folder_row(frame, 0, "Watched folder:", self.watch_var)
        self.root_entry, self.root_btn = self._folder_row(frame, 1, "Workflows folder:", self.root_var)

        ttk.Label(frame, text="Subfolder:").grid(row=2, column=0, sticky="w", pady=3)
        self.sub_combo = ttk.Combobox(frame, textvariable=self.sub_var, state="readonly",
                                      postcommand=self._refresh_subfolders)
        self.sub_combo.grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text="New…", command=self._new_subfolder).grid(row=2, column=2, padx=(5, 0))

        ttk.Checkbutton(frame, text="Also process files already present when starting",
                        variable=self.existing_var).grid(row=3, column=0, columnspan=3, sticky="w", pady=3)
        try:
            enabled = autostart.is_enabled()
            if enabled:
                autostart.enable()  # rewrites the Run entry with the current command (e.g. after an update)
        except OSError:
            enabled = False
        self.autostart_var = tk.BooleanVar(value=enabled)
        ttk.Checkbutton(frame, text="Start at Windows sign-in (minimized, watching)",
                        variable=self.autostart_var).grid(row=4, column=0, columnspan=3, sticky="w", pady=3)
        self.autostart_var.trace_add("write", lambda *_: self._apply_autostart())

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=6)
        buttons.columnconfigure(0, weight=1)
        self.toggle_btn = ttk.Button(buttons, text="Start", command=self._toggle)
        self.toggle_btn.grid(row=0, column=0, sticky="ew")
        self.retry_btn = ttk.Button(buttons, text="Retry errors", command=self._retry,
                                    state="disabled")
        self.retry_btn.grid(row=0, column=1, padx=(5, 0))
        self.shortcut_btn = ttk.Button(buttons, text="Create desktop shortcut",
                                       command=self._create_shortcut)
        self.shortcut_btn.grid(row=0, column=2, padx=(5, 0))

        self.log = tk.Text(frame, height=14, state="disabled", wrap="word")
        self.log.grid(row=6, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(6, weight=1)
        self.log.tag_configure("ok", foreground="#1a7f37")
        self.log.tag_configure("ignored", foreground="#777777")
        self.log.tag_configure("error", foreground="#cf222e")
        self.log.tag_configure("warn", foreground="#b35900")

        for var in (self.watch_var, self.root_var, self.sub_var, self.existing_var):
            var.trace_add("write", lambda *_: self._save())
        self._refresh_subfolders()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.bind("<Unmap>", self._on_unmap)
        self._schedule(200, self._drain)
        self._schedule(HEALTH_CHECK_MS, self._check_health)
        self._set_running(False)
        self._update_shortcut_button()
        if at_login:
            self._hide_to_tray()
            self._toggle()
        elif not self.cfg["desktop_shortcut_asked"] and not self._shortcut_exists():
            self._schedule(300, self._offer_shortcut)

    # --- Building -------------------------------------------------------------

    def _set_window_icon(self) -> list:
        """Title bar and taskbar icon (the images must stay referenced)."""
        images = [logo.icon_image(size) for size in (64, 32, 16)]
        if any(img is None for img in images):
            return []
        photos = [ImageTk.PhotoImage(img, master=self.root) for img in images]
        self.root.iconphoto(False, *photos)
        return photos

    def _build_banner(self):
        """Logo banner at the top of the window; absent if the logo file is missing."""
        img = logo.banner_image(420)
        if img is None:
            return None
        self._banner_photo = ImageTk.PhotoImage(img, master=self.root)
        band = tk.Frame(self.root, background=logo.BANNER_BACKGROUND)
        band.pack(fill="x")
        label = tk.Label(band, image=self._banner_photo, background=logo.BANNER_BACKGROUND, borderwidth=0)
        label.pack()
        return label

    def _folder_row(self, frame, row, label, var):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(frame, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=3)

        def browse():
            chosen = filedialog.askdirectory(initialdir=var.get() or None)
            if chosen:
                var.set(str(Path(chosen)))
                self._refresh_subfolders()

        button = ttk.Button(frame, text="Browse…", command=browse)
        button.grid(row=row, column=2, padx=(5, 0))
        return entry, button

    # --- Subfolders -----------------------------------------------------------

    def _refresh_subfolders(self) -> None:
        root = Path(self.root_var.get())
        try:
            names = sorted((p.name for p in root.iterdir()
                            if p.is_dir() and not p.name.startswith(".")), key=str.lower)
        except OSError:
            names = []
        self.sub_combo["values"] = [ROOT_LABEL, *names]

    def _new_subfolder(self) -> None:
        name = simpledialog.askstring("New subfolder", "Subfolder name:", parent=self.root)
        if name is None:
            return
        if not valid_subfolder_name(name):
            messagebox.showerror(
                "Invalid name",
                "The name must not start with a dot or contain \\ / : * ? \" < > |",
                parent=self.root)
            return
        name = name.strip()
        try:
            (Path(self.root_var.get()) / name).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Error", f"Cannot create the folder:\n{e}", parent=self.root)
            return
        self._refresh_subfolders()
        self.sub_var.set(name)

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
            self._write("Watching stopped.", "ignored")
            return
        watch_dir, root = Path(self.watch_var.get()), Path(self.root_var.get())
        if not watch_dir.is_dir():
            self._write(f"Error: the watched folder does not exist - {watch_dir}", "error")
            return
        if not root.is_dir():
            self._write(f"Error: the workflows folder does not exist - {root}", "error")
            return
        self.watcher = FolderWatcher(watch_dir, self._dest, self.results.put)
        try:
            self.watcher.start(process_existing=self.existing_var.get())
        except OSError as e:
            self._write(f"Error: cannot watch {watch_dir} - {e}", "error")
            return
        self._set_running(True)
        self._write(f"Watching {watch_dir}.", "ignored")

    def _retry(self) -> None:
        if self.watcher and self.watcher.running and self.watcher.failed_count:
            self._write(f"Retrying {self.watcher.failed_count} file(s)…", "ignored")
            self.watcher.retry_failed()
        self._update_retry()

    def _update_retry(self) -> None:
        active = bool(self.watcher and self.watcher.running and self.watcher.failed_count)
        self.retry_btn.configure(state="normal" if active else "disabled")

    def _check_health(self) -> None:
        if self.watcher and self.watcher.running and not self.watcher.healthy:
            self.watcher.stop()
            self._set_running(False)
            self._write(f"Error: watching interrupted, the folder {self.watcher.watch_dir} "
                        "cannot be found. Check it, then click Start.", "error")
        self._schedule(HEALTH_CHECK_MS, self._check_health)

    # --- Desktop shortcut -----------------------------------------------------

    def _shortcut_exists(self) -> bool:
        try:
            return shortcut.exists()
        except OSError:
            return False

    def _update_shortcut_button(self) -> None:
        self.shortcut_btn.configure(state="disabled" if self._shortcut_exists() else "normal")

    def _create_shortcut(self) -> None:
        try:
            path = shortcut.create()
        except OSError as e:
            self._write(f"Error: shortcut not created - {e}", "error")
        else:
            self._write(f"Shortcut created on the desktop: {path}", "ok")
        self._update_shortcut_button()

    def _offer_shortcut(self) -> None:
        """First launch: offers the desktop shortcut, only once whatever the answer."""
        self.cfg["desktop_shortcut_asked"] = True
        self._save()
        if choice_dialog(self.root, TITLE, f"Create a {TITLE} shortcut on the desktop?",
                         [("Yes, create it", True), ("No thanks", False)]) is True:
            self._create_shortcut()

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for widget in (self.watch_entry, self.watch_btn, self.root_entry, self.root_btn):
            widget.configure(state=state)
        self.toggle_btn.configure(text="Stop" if running else "Start")
        self.tray.set_tooltip(f"{TITLE} — watching: {'active' if running else 'stopped'}")
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
        while True:
            try:
                result: ImportResult = self.results.get_nowait()
            except queue.Empty:
                break
            name = result.source.name
            if result.status == "imported":
                self._write(f"Imported: {name} → {result.target}", "ok")
                if result.message:
                    self._write(f"Warning: {result.message}", "warn")
            elif result.status == "ignored":
                self._write(f"Ignored (not a workflow): {name}", "ignored")
            else:
                self._write(f"Error: {name} - {result.message} "
                            "(fix it, then click \"Retry errors\")", "error")
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
            "subfolder": "" if sub == ROOT_LABEL else sub,
            "process_existing": self.existing_var.get(),
            "desktop_shortcut_asked": self.cfg.get("desktop_shortcut_asked", False),
        }
        try:
            save_config(self.cfg)
        except OSError as e:
            self._write(f"Error: settings not saved - {e}", "error")

    def _apply_autostart(self) -> None:
        wanted = self.autostart_var.get()
        try:
            autostart.enable() if wanted else autostart.disable()
        except OSError as e:
            self._write(f"Error: start at sign-in not changed - {e}", "error")
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
            self.root, "Close",
            f"Do you want to minimize {TITLE} to the notification area\n"
            "(watching continues) or quit it?",
            [("Minimize to tray", "minimize"), ("Quit", "quit"), ("Cancel", None)])

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
    instance = single_instance.SingleInstance()
    if not instance.acquire():
        # Already running: at sign-in, leave silently; otherwise ask.
        if not at_login:
            root = tk.Tk()
            root.withdraw()
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
