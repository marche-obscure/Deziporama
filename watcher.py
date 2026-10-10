"""Watches the download folder and imports the workflows arriving there."""

import queue
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from i18n import t
from importer import ImportResult, import_file

EXTENSIONS = {".json", ".zip"}
READY_INTERVAL = 1.0
READY_TIMEOUT = 120.0


def is_candidate(path: Path) -> bool:
    return Path(path).suffix.lower() in EXTENSIONS


def wait_until_ready(path: Path, timeout: float | None = None,
                     interval: float | None = None,
                     stop: threading.Event | None = None) -> bool:
    """Waits until the file size is stable over 2 checks and the file is readable."""
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
        self._failed: set[Path] = set()
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None

    @property
    def healthy(self) -> bool:
        """False if watching stopped on its own (folder gone, observer stopped)."""
        return (self._observer is not None and self._observer.is_alive()
                and self.watch_dir.is_dir())

    @property
    def failed_count(self) -> int:
        with self._lock:
            return len(self._failed)

    def retry_failed(self) -> None:
        """Queues again the files whose import failed (e.g. drive back)."""
        with self._lock:
            paths, self._failed = sorted(self._failed), set()
        for path in paths:
            self._seen.pop(path, None)
            self._todo.put(path)

    def start(self, process_existing: bool = False) -> None:
        if self.running:
            return
        self._todo = queue.Queue()
        self._stop = threading.Event()
        # The observer starts before existing files are listed: a file arriving in between
        # is seen at least once (duplicates are discarded by _process).
        observer = Observer()
        observer.schedule(_Handler(self._todo), str(self.watch_dir), recursive=False)
        observer.start()
        self._observer = observer
        if process_existing:
            for path in sorted(self.watch_dir.iterdir()):
                if path.is_file() and is_candidate(path):
                    self._todo.put(path)
        self._thread = threading.Thread(target=self._work, args=(self._todo, self._stop), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        if self._thread is not None:
            # Pending files are dropped; only the file in progress finishes.
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
            except Exception as e:  # noqa: BLE001 - the thread must never die
                self._on_result(ImportResult("error", path, None, str(e)))

    def _process(self, path: Path, stop: threading.Event) -> None:
        # File already handled (moved) or duplicate event: ignore.
        signature = self._signature(path)
        if signature is None or self._seen.get(path) == signature:
            return
        if not wait_until_ready(path, stop=stop):
            if stop.is_set():
                return
            result = ImportResult("error", path, None,
                                  t("msg_download_unfinished", seconds=READY_TIMEOUT))
        elif path.stat().st_size == 0:
            # Empty placeholder created by the browser (Firefox): the real content arrives by rename.
            return
        else:
            result = import_file(path, Path(self._get_dest()))
        self._seen[path] = self._signature(path)
        if result.status == "error":
            with self._lock:
                self._failed.add(path)
        self._on_result(result)
