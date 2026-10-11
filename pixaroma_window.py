"""Window listing the Pixaroma episodes, to import them directly."""

import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk
from typing import Callable

import pixaroma
from i18n import t
from importer import ImportResult
from ui import center_on_screen

COLUMNS = (("number", "col_number", 50), ("title", "col_title", 430), ("category", "col_category", 90),
           ("workflows", "col_workflows", 80), ("size", "col_size", 80), ("status", "col_status", 100))


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _in_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class PixaromaWindow:
    """Network work runs through `run_background`; its results come back through a queue
    read on the Tk thread (process_queue), so Tkinter is only touched from the Tk thread."""

    def __init__(self, parent, pixaroma_dir: Path, last_seen: int, *,
                 fetch: Callable[[], list] = pixaroma.fetch_episodes,
                 import_episode: Callable[[pixaroma.Episode, Path], ImportResult] = pixaroma.import_episode,
                 on_message: Callable[[str, str], None], on_result: Callable[[ImportResult], None],
                 on_seen: Callable[[int], None],
                 run_background: Callable[[Callable[[], None]], None] = _in_thread) -> None:
        self.pixaroma_dir = Path(pixaroma_dir)
        self.last_seen = last_seen
        self._fetch, self._import = fetch, import_episode
        self._on_message, self._on_result, self._on_seen = on_message, on_result, on_seen
        self._run_background = run_background
        self._queue: queue.Queue = queue.Queue()
        self.episodes: list[pixaroma.Episode] = []

        self.window = tk.Toplevel(parent)
        self.window.title(t("pixaroma_title"))
        self.window.minsize(760, 420)
        frame = ttk.Frame(self.window, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(top, text=t("pixaroma_category")).pack(side="left")
        self.category_var = tk.StringVar(value=t("pixaroma_all_categories"))
        self.category_combo = ttk.Combobox(top, textvariable=self.category_var, state="readonly", width=14)
        self.category_combo.pack(side="left", padx=(5, 0))
        self.category_var.trace_add("write", lambda *_: self._show_rows())
        ttk.Button(top, text=t("pixaroma_refresh"), command=self.load).pack(side="right")

        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS], show="headings", selectmode="extended")
        for column, key, width in COLUMNS:
            self.tree.heading(column, text=t(key))
            self.tree.column(column, width=width, stretch=column == "title",
                             anchor="w" if column in ("title", "category", "status") else "e")
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda e: self.open_video())

        bottom = ttk.Frame(frame)
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.status_label = ttk.Label(bottom, text=t("pixaroma_hint"))
        self.status_label.pack(side="left")
        self.import_btn = ttk.Button(bottom, text=t("pixaroma_import"), command=self.import_selected)
        self.import_btn.pack(side="right")

        center_on_screen(self.window)
        self.load()
        self._poll()

    # --- Background work --------------------------------------------------------

    def _poll(self) -> None:
        if self.window.winfo_exists():
            self.process_queue()
            self.window.after(150, self._poll)

    def process_queue(self) -> None:
        """Applies on the Tk thread what the background work produced."""
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                return
            if kind == "episodes":
                self._set_episodes(payload)
            elif kind == "failed":
                self.status_label.configure(text=t("pixaroma_list_failed", error=payload))
            elif kind == "imported":
                self.import_btn.configure(state="normal")
                self._show_rows()

    def load(self) -> None:
        self.status_label.configure(text=t("pixaroma_loading"))

        def work():
            try:
                self._queue.put(("episodes", self._fetch()))
            except pixaroma.PixaromaError as e:
                self._queue.put(("failed", str(e)))

        self._run_background(work)

    def import_selected(self) -> None:
        chosen = [ep for ep in self.episodes if str(ep.number) in self.tree.selection()]
        if not chosen:
            return
        self.import_btn.configure(state="disabled")

        def work():
            for ep in chosen:
                self._on_message(t("log_pixaroma_downloading", name=ep.zip_name), "ignored")
                self._on_result(self._import(ep, self.pixaroma_dir))
            self._queue.put(("imported", None))

        self._run_background(work)

    # --- Display ----------------------------------------------------------------

    def _set_episodes(self, episodes: list) -> None:
        self.episodes = episodes
        self.category_combo["values"] = self.category_choices()
        self.status_label.configure(text=t("pixaroma_hint"))
        self._show_rows()
        if episodes:
            self._on_seen(max(ep.number for ep in episodes))

    def category_choices(self) -> list[str]:
        return [t("pixaroma_all_categories"), *sorted({ep.category for ep in self.episodes if ep.category})]

    def _status(self, episode: pixaroma.Episode, imported: set[int]) -> str:
        if episode.number in imported:
            return t("status_imported")
        if episode.coming_soon:
            return t("status_coming_soon")
        if episode.number > self.last_seen:
            return t("status_new")
        return ""

    def _show_rows(self) -> None:
        selection = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        imported = pixaroma.imported_numbers(self.pixaroma_dir)
        category = self.category_var.get()
        for ep in self.episodes:
            if category != t("pixaroma_all_categories") and ep.category != category:
                continue
            self.tree.insert("", "end", iid=str(ep.number), values=(
                ep.number, ep.title, ep.category, ep.workflow_count, format_size(ep.size),
                self._status(ep, imported)))
        self.tree.selection_set([i for i in selection if self.tree.exists(i)])

    def open_video(self) -> None:
        for ep in self.episodes:
            if str(ep.number) in self.tree.selection() and ep.youtube:
                webbrowser.open(ep.youtube)
                return
