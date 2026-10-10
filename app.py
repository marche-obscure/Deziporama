"""Fenêtre de l'importeur de workflows ComfyUI."""

import json
import os
import queue
import re
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import autostart
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
}
ROOT_LABEL = "(racine)"
HEALTH_CHECK_MS = 2000
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def valid_subfolder_name(name: str) -> bool:
    """Un seul niveau de dossier, dans la racine des workflows, nom autorisé par Windows."""
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
    # Écriture dans un fichier temporaire puis remplacement : un plantage ne perd pas les réglages.
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def choice_dialog(parent, title: str, message: str, buttons: list[tuple[str, object]]):
    """Boîte modale à boutons ; renvoie la valeur du bouton cliqué (None si fermée)."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.resizable(False, False)
    # Rattachée à une fenêtre cachée, Windows ne l'afficherait jamais (cas de la deuxième copie).
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
    dialog.grab_set()
    parent.wait_window(dialog)
    return choice["value"]


def ask_already_running(parent) -> bool:
    """Avertit d'un double lancement ; vrai si l'utilisateur veut afficher la copie déjà lancée."""
    return choice_dialog(
        parent, "Déjà lancé",
        "L'importeur de workflows est déjà lancé\n"
        "(son icône se trouve près de l'horloge).\n\n"
        "Voulez-vous afficher sa fenêtre ?",
        [("Afficher celui déjà lancé", True), ("Annuler", False)]) is True


def is_login_start(argv: list[str]) -> bool:
    """Vrai si l'applicatif a été lancé par Windows à l'ouverture de session."""
    return autostart.STARTUP_FLAG in argv[1:]


class App:
    def __init__(self, root: tk.Tk, at_login: bool = False) -> None:
        self.root = root
        self.cfg = load_config()
        self.results: queue.Queue = queue.Queue()
        self.commands: queue.Queue = queue.Queue()  # ordres venant de l'icône (autre thread)
        self.watcher: FolderWatcher | None = None
        self._scheduled: dict[str, str] = {}
        self.tray = TrayIcon(on_show=lambda: self.commands.put("show"),
                             on_quit=lambda: self.commands.put("quit"))

        root.title(TITLE)
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
        try:
            enabled = autostart.is_enabled()
        except OSError:
            enabled = False
        self.autostart_var = tk.BooleanVar(value=enabled)
        ttk.Checkbutton(frame, text="Lancer à l'ouverture de session Windows (réduit, surveillance démarrée)",
                        variable=self.autostart_var).grid(row=4, column=0, columnspan=3, sticky="w", pady=3)
        self.autostart_var.trace_add("write", lambda *_: self._apply_autostart())

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=6)
        buttons.columnconfigure(0, weight=1)
        self.toggle_btn = ttk.Button(buttons, text="Démarrer", command=self._toggle)
        self.toggle_btn.grid(row=0, column=0, sticky="ew")
        self.retry_btn = ttk.Button(buttons, text="Réessayer les erreurs", command=self._retry,
                                    state="disabled")
        self.retry_btn.grid(row=0, column=1, padx=(5, 0))

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
        if at_login:
            self._hide_to_tray()
            self._toggle()

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
        if name is None:
            return
        if not valid_subfolder_name(name):
            messagebox.showerror(
                "Nom invalide",
                "Le nom ne doit pas commencer par un point ni contenir \\ / : * ? \" < > |",
                parent=self.root)
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

    def _retry(self) -> None:
        if self.watcher and self.watcher.running and self.watcher.failed_count:
            self._write(f"Nouvelle tentative pour {self.watcher.failed_count} fichier(s)…", "ignored")
            self.watcher.retry_failed()
        self._update_retry()

    def _update_retry(self) -> None:
        active = bool(self.watcher and self.watcher.running and self.watcher.failed_count)
        self.retry_btn.configure(state="normal" if active else "disabled")

    def _check_health(self) -> None:
        if self.watcher and self.watcher.running and not self.watcher.healthy:
            self.watcher.stop()
            self._set_running(False)
            self._write(f"Erreur : surveillance interrompue, le dossier {self.watcher.watch_dir} "
                        "est introuvable. Vérifiez-le puis cliquez sur Démarrer.", "error")
        self._schedule(HEALTH_CHECK_MS, self._check_health)

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for widget in (self.watch_entry, self.watch_btn, self.root_entry, self.root_btn):
            widget.configure(state=state)
        self.toggle_btn.configure(text="Arrêter" if running else "Démarrer")
        self.tray.set_tooltip(f"{TITLE} — surveillance {'active' if running else 'arrêtée'}")
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
                self._write(f"Importé : {name} → {result.target}", "ok")
                if result.message:
                    self._write(f"Attention : {result.message}", "warn")
            elif result.status == "ignored":
                self._write(f"Ignoré (pas un workflow) : {name}", "ignored")
            else:
                self._write(f"Erreur : {name} — {result.message} "
                            "(corrigez puis cliquez sur « Réessayer les erreurs »)", "error")
        self._update_retry()
        self._schedule(200, self._drain)

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

    def _apply_autostart(self) -> None:
        wanted = self.autostart_var.get()
        try:
            autostart.enable() if wanted else autostart.disable()
        except OSError as e:
            self._write(f"Erreur : lancement à l'ouverture de session non modifié — {e}", "error")
            if self.autostart_var.get() != (not wanted):
                self.autostart_var.set(not wanted)

    # --- Zone de notification et fermeture ------------------------------------

    def _on_unmap(self, event) -> None:
        # Bouton « Réduire » : la fenêtre quitte la barre des tâches pour la zone de notification.
        if event.widget is self.root and self.root.state() == "iconic":
            self._hide_to_tray()

    def _hide_to_tray(self) -> None:
        self.root.withdraw()
        self.tray.show()

    def _show_window(self) -> None:
        self.tray.hide()
        self.root.deiconify()
        self.root.lift()
        # Rappelée par une autre copie, Windows laisserait la fenêtre derrière les autres.
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def _ask_close(self) -> str | None:
        """Boîte « Réduire / Quitter / Annuler ». Renvoie "minimize", "quit" ou None."""
        return choice_dialog(
            self.root, "Fermer",
            "Voulez-vous réduire l'applicatif près de l'horloge\n"
            "(la surveillance continue) ou le quitter ?",
            [("Réduire près de l'horloge", "minimize"), ("Quitter", "quit"), ("Annuler", None)])

    def _close(self) -> None:
        choice = self._ask_close()
        if choice == "minimize":
            self._hide_to_tray()
        elif choice == "quit":
            self._quit()

    def _schedule(self, ms: int, callback) -> None:
        """root.after mémorisé par fonction, pour pouvoir tout annuler en quittant."""
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
        # Déjà lancé : au démarrage de session on se retire sans bruit, sinon on demande.
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
