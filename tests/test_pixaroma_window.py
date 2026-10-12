import tkinter as tk
from pathlib import Path

import pytest

import i18n
import pixaroma
import pixaroma_window
from importer import ImportResult
from tests.test_pixaroma import episode_data, episodes_js


@pytest.fixture(scope="module")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def five_episodes():
    return pixaroma.parse_episodes(episodes_js(
        episode_data(1, "One", category="Basics"), episode_data(2, "Two"),
        episode_data(3, "Three", category="Video"), episode_data(4, "Four", category="Video"),
        episode_data(5, "Five", coming_soon=True)))


@pytest.fixture
def make(tk_root, tmp_path):
    windows = []
    calls = {"messages": [], "results": [], "seen": [], "imported": [], "recorded": [], "ignore": []}

    def fake_import(episode, dest):
        calls["imported"].append(episode.number)
        target = Path(dest) / episode.folder_name
        target.mkdir(parents=True)
        return ImportResult("imported", Path(episode.zip_name), target)

    def build(fetch=None, last_seen=3, ignored=()):
        w = pixaroma_window.PixaromaWindow(
            tk_root, tmp_path / "2026", last_seen, scan_dir=tmp_path, ignored=set(ignored),
            on_imported=calls["recorded"].append,
            on_ignore=lambda numbers, flag: calls["ignore"].append((sorted(numbers), flag)),
            fetch=fetch or five_episodes, import_episode=fake_import,
            on_message=lambda text, tag: calls["messages"].append((text, tag)),
            on_result=calls["results"].append, on_seen=calls["seen"].append,
            run_background=lambda fn: fn())
        w.process_queue()
        windows.append(w)
        return w

    build.calls = calls
    yield build
    for w in windows:
        if w.window.winfo_exists():
            w.window.destroy()


def rows(w):
    return [w.tree.item(i, "values") for i in w.tree.get_children()]


def test_lists_episodes_newest_first_with_status(make, tmp_path):
    (tmp_path / "2025" / "Ep02 - Two").mkdir(parents=True)  # imported earlier, in another subfolder
    w = make(last_seen=3)
    assert [(r[0], r[1], r[5]) for r in rows(w)] == [
        ("5", "Five", "New"), ("4", "Four", "New"), ("3", "Three", "Not imported"),
        ("2", "Two", "Imported"), ("1", "One", "Not imported")]
    assert rows(w)[1][2:5] == ("Video", "2", "1.2 KB")


def test_reports_newest_episode_as_seen(make):
    make(last_seen=3)
    assert make.calls["seen"] == [5]


def test_category_filter(make):
    w = make()
    assert w.category_choices() == ["All", "Basics", "Image", "Video"]
    w.category_var.set("Video")
    assert [r[0] for r in rows(w)] == ["4", "3"]
    w.category_var.set("All")
    assert len(rows(w)) == 5


def test_import_selected(make, tmp_path):
    w = make()
    w.tree.selection_set(["4", "1"])
    w.import_selected()
    w.process_queue()
    assert make.calls["imported"] == [4, 1]
    assert [r.status for r in make.calls["results"]] == ["imported", "imported"]
    assert make.calls["messages"][0] == ("Downloading Ep4 Workflows.zip…", "ignored")
    statuses = {r[0]: r[5] for r in rows(w)}
    assert statuses["4"] == "Imported" and statuses["1"] == "Imported"
    assert (tmp_path / "2026" / "Ep04 - Four").is_dir()


def test_import_without_selection_does_nothing(make):
    w = make()
    w.import_selected()
    assert make.calls["imported"] == []


def test_list_failure_is_shown(make):
    def broken():
        raise pixaroma.PixaromaError("offline")

    w = make(fetch=broken)
    assert rows(w) == []
    assert w.status_label.cget("text") == "The Pixaroma episode list could not be read: offline"


def test_double_click_opens_video(make, monkeypatch):
    opened = []
    monkeypatch.setattr(pixaroma_window.webbrowser, "open", opened.append)
    w = make()
    w.tree.selection_set(["3"])
    w.open_video()
    assert opened == ["https://www.youtube.com/watch?v=3"]


def test_texts_follow_language(make):
    i18n.set_language("fr")
    w = make()
    assert w.window.title() == "Épisodes Pixaroma"
    assert w.tree.heading("status", "text") == "État"
    assert rows(w)[1][5] == "Nouveau"



# --- History and ignored episodes ---------------------------------------------------

def test_coming_soon_not_imported(make):
    w = make(last_seen=5)
    assert rows(w)[0][5] == "Coming soon – not imported"


def test_ignored_status(make):
    w = make(ignored={1, 3})
    statuses = {r[0]: r[5] for r in rows(w)}
    assert statuses["1"] == "Ignored" and statuses["3"] == "Ignored"


def test_ignore_and_offer_again_selected(make):
    w = make()
    w.tree.selection_set(["1", "3"])
    w.ignore_selected()
    assert make.calls["ignore"] == [([1, 3], True)]
    assert {r[0]: r[5] for r in rows(w)}["3"] == "Ignored"
    w.tree.selection_set(["3"])
    w.offer_again_selected()
    assert make.calls["ignore"][-1] == ([3], False)
    assert {r[0]: r[5] for r in rows(w)}["3"] == "Not imported"


def test_import_records_history_and_unignores(make):
    w = make(ignored={4})
    w.tree.selection_set(["4"])
    w.import_selected()
    w.process_queue()
    assert make.calls["recorded"] == [4]
    assert {r[0]: r[5] for r in rows(w)}["4"] == "Imported"
    assert 4 not in w.ignored


def test_ignore_buttons_translated(make):
    i18n.set_language("fr")
    w = make()
    assert w.ignore_btn.cget("text") == "Ne plus proposer"
    assert w.offer_again_btn.cget("text") == "Proposer à nouveau"
