"""Surveillance du dossier de téléchargement et import des workflows qui y arrivent."""

import queue
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from importer import ImportResult, import_file

EXTENSIONS = {".json", ".zip"}
READY_INTERVAL = 1.0
READY_TIMEOUT = 120.0


def is_candidate(path: Path) -> bool:
    return Path(path).suffix.lower() in EXTENSIONS


def wait_until_ready(path: Path, timeout: float | None = None,
                     interval: float | None = None,
                     stop: threading.Event | None = None) -> bool:
    """Attend que la taille du fichier soit stable sur 2 contrôles et qu'il soit lisible."""
    timeout = READY_TIMEOUT if timeout is None else timeout
    interval = READY_INTERVAL if interval is None else interval
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        if stop is not None and stop.is_set():
            return False
        try:
            size = path.stat().st_size
            if size == previous:
                with open(path, "rb"):
                    return True
            previous = size
        except OSError:
            previous = None
        time.sleep(interval)
    return False


class _Handler(FileSystemEventHandler):
    def __init__(self, todo: queue.Queue):
        self._todo = todo

    def _push(self, raw: str) -> None:
        path = Path(raw)
        if is_candidate(path):
            self._todo.put(path)

    def on_created(self, event):
        if not event.is_directory:
            self._push(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._push(event.dest_path)


class FolderWatcher:
    def __init__(self, watch_dir: Path, get_dest: Callable[[], Path],
                 on_result: Callable[[ImportResult], None]) -> None:
        self.watch_dir = Path(watch_dir)
        self._get_dest = get_dest
        self._on_result = on_result
        self._observer = None
        self._thread = None
        self._todo: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._seen: dict[Path, tuple[int, int]] = {}

    @property
    def running(self) -> bool:
        return self._thread is not None

    def start(self, process_existing: bool = False) -> None:
        if self.running:
            return
        self._todo = queue.Queue()
        self._stop = threading.Event()
        if process_existing:
            for path in sorted(self.watch_dir.iterdir()):
                if path.is_file() and is_candidate(path):
                    self._todo.put(path)
        observer = Observer()
        observer.schedule(_Handler(self._todo), str(self.watch_dir), recursive=False)
        observer.start()
        self._observer = observer
        self._thread = threading.Thread(target=self._work, args=(self._todo, self._stop), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        if self._thread is not None:
            # On abandonne les fichiers en attente ; seul le fichier en cours se termine.
            self._stop.set()
            while True:
                try:
                    self._todo.get_nowait()
                except queue.Empty:
                    break
            self._todo.put(None)
            self._thread.join(timeout=1.0)
            self._thread = None

    def _signature(self, path: Path) -> tuple[int, int] | None:
        try:
            st = path.stat()
            return st.st_size, st.st_mtime_ns
        except OSError:
            return None

    def _work(self, todo: queue.Queue, stop: threading.Event) -> None:
        while True:
            path = todo.get()
            if path is None or stop.is_set():
                return
            try:
                self._process(path, stop)
            except Exception as e:  # noqa: BLE001 — le thread ne doit jamais mourir
                self._on_result(ImportResult("error", path, None, str(e)))

    def _process(self, path: Path, stop: threading.Event) -> None:
        # Fichier déjà traité (déplacé) ou événement en double : on ignore.
        signature = self._signature(path)
        if signature is None or self._seen.get(path) == signature:
            return
        if not wait_until_ready(path, stop=stop):
            if stop.is_set():
                return
            result = ImportResult("error", path, None,
                                  f"téléchargement non terminé après {READY_TIMEOUT:.0f} s")
        elif path.stat().st_size == 0:
            # Fichier vide réservé par le navigateur (Firefox) : le vrai contenu arrivera par renommage.
            return
        else:
            result = import_file(path, Path(self._get_dest()))
        self._seen[path] = self._signature(path)
        self._on_result(result)
