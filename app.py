"""Fenêtre de l'importeur de workflows ComfyUI."""

import json
import queue
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from importer import ImportResult
from watcher import FolderWatcher

CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULTS = {
    "watch_dir": str(Path.home() / "Downloads"),
    "workflows_root": r"G:\GenerateurIA\ComfyUI\User\default\workflows",
    "subfolder": "",
    "process_existing": False,
}
ROOT_LABEL = "(racine)"


def load_config(path: Path = CONFIG_PATH) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    return {key: data.get(key, default) for key, default in DEFAULTS.items()}


def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    Path(path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.cfg = load_config()
        self.results: queue.Queue = queue.Queue()
        self.watcher: FolderWatcher | None = None

        root.title("Importeur de workflows ComfyUI")
        root.minsize(640, 420)
        frame = ttk.Frame(root, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self.watch_var = tk.StringVar(value=self.cfg["watch_dir"])
        self.root_var = tk.StringVar(value=self.cfg["workflows_root"])
        self.sub_var = tk.StringVar(value=self.cfg["subfolder"] or ROOT_LABEL)
        self.existing_var = tk.BooleanVar(value=self.cfg["process_existing"])

        self.watch_entry, self.watch_btn = self._folder_row(frame, 0, "Dossier surveillé :", self.watch_var)
        self.root_entry, self.root_btn = self._folder_row(frame, 1, "Dossier des workflows :", self.root_var)

        ttk.Label(frame, text="Sous-dossier :").grid(row=2, column=0, sticky="w", pady=3)
        self.sub_combo = ttk.Combobox(frame, textvariable=self.sub_var, state="readonly",
                                      postcommand=self._refresh_subfolders)
        self.sub_combo.grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text="Nouveau…", command=self._new_subfolder).grid(row=2, column=2, padx=(5, 0))

        ttk.Checkbutton(frame, text="Traiter aussi les fichiers déjà présents au démarrage",
                        variable=self.existing_var).grid(row=3, column=0, columnspan=3, sticky="w", pady=3)

        self.toggle_btn = ttk.Button(frame, text="Démarrer", command=self._toggle)
        self.toggle_btn.grid(row=4, column=0, columnspan=3, sticky="ew", pady=6)

        self.log = tk.Text(frame, height=14, state="disabled", wrap="word")
        self.log.grid(row=5, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(5, weight=1)
        self.log.tag_configure("ok", foreground="#1a7f37")
        self.log.tag_configure("ignored", foreground="#777777")
        self.log.tag_configure("error", foreground="#cf222e")
        self.log.tag_configure("warn", foreground="#b35900")

        for var in (self.watch_var, self.root_var, self.sub_var, self.existing_var):
            var.trace_add("write", lambda *_: self._save())
        self._refresh_subfolders()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(200, self._drain)

    # --- Construction ---------------------------------------------------------

    def _folder_row(self, frame, row, label, var):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(frame, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=3)

        def browse():
            chosen = filedialog.askdirectory(initialdir=var.get() or None)
            if chosen:
                var.set(str(Path(chosen)))
                self._refresh_subfolders()

        button = ttk.Button(frame, text="Parcourir…", command=browse)
        button.grid(row=row, column=2, padx=(5, 0))
        return entry, button

    # --- Sous-dossiers --------------------------------------------------------

    def _refresh_subfolders(self) -> None:
        root = Path(self.root_var.get())
        try:
            names = sorted((p.name for p in root.iterdir()
                            if p.is_dir() and not p.name.startswith(".")), key=str.lower)
        except OSError:
            names = []
        self.sub_combo["values"] = [ROOT_LABEL, *names]

    def _new_subfolder(self) -> None:
        name = simpledialog.askstring("Nouveau sous-dossier", "Nom du sous-dossier :", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        try:
            (Path(self.root_var.get()) / name).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Erreur", f"Impossible de créer le dossier :\n{e}", parent=self.root)
            return
        self._refresh_subfolders()
        self.sub_var.set(name)

    def _dest(self) -> Path:
        # Appelé depuis le thread de surveillance : ne lit que la config, jamais Tkinter.
        cfg = self.cfg
        root = Path(cfg["workflows_root"])
        return root / cfg["subfolder"] if cfg["subfolder"] else root

    # --- Surveillance ---------------------------------------------------------

    def _toggle(self) -> None:
        if self.watcher and self.watcher.running:
            self.watcher.stop()
            self._set_running(False)
            self._write("Surveillance arrêtée.", "ignored")
            return
        watch_dir, root = Path(self.watch_var.get()), Path(self.root_var.get())
        if not watch_dir.is_dir():
            self._write(f"Erreur : le dossier surveillé n'existe pas — {watch_dir}", "error")
            return
        if not root.is_dir():
            self._write(f"Erreur : le dossier des workflows n'existe pas — {root}", "error")
            return
        self.watcher = FolderWatcher(watch_dir, self._dest, self.results.put)
        try:
            self.watcher.start(process_existing=self.existing_var.get())
        except OSError as e:
            self._write(f"Erreur : impossible de surveiller {watch_dir} — {e}", "error")
            return
        self._set_running(True)
        self._write(f"Surveillance de {watch_dir} démarrée.", "ignored")

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for widget in (self.watch_entry, self.watch_btn, self.root_entry, self.root_btn):
            widget.configure(state=state)
        self.toggle_btn.configure(text="Arrêter" if running else "Démarrer")

    def _drain(self) -> None:
        while True:
            try:
                result: ImportResult = self.results.get_nowait()
            except queue.Empty:
                break
            name = result.source.name
            if result.status == "imported":
                self._write(f"Importé : {name} → {result.target}", "ok")
                if result.message:
                    self._write(f"Attention : {result.message}", "warn")
            elif result.status == "ignored":
                self._write(f"Ignoré (pas un workflow) : {name}", "ignored")
            else:
                self._write(f"Erreur : {name} — {result.message}", "error")
        self.root.after(200, self._drain)

    # --- Divers ---------------------------------------------------------------

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
        }
        try:
            save_config(self.cfg)
        except OSError as e:
            self._write(f"Erreur : réglages non sauvegardés — {e}", "error")

    def _close(self) -> None:
        if self.watcher:
            self.watcher.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
