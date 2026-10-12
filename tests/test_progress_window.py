import tkinter as tk

import pytest

import i18n
import progress_window


@pytest.fixture(scope="module")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def window(tk_root):
    w = progress_window.ProgressWindow(tk_root)
    yield w
    w.close()


def test_download_phase(window):
    window.update("Ep38 - Title", 1, 2, "download", 250, 1000)
    assert window.episode_label.cget("text") == "Ep38 - Title (1/2)"
    assert window.phase_label.cget("text") == "Downloading…"
    assert window.bar["value"] == 25
    assert window.percent_label.cget("text") == "25 %"


def test_extract_phase(window):
    window.update("Ep39 - Other", 2, 2, "extract", 1000, 1000)
    assert window.phase_label.cget("text") == "Extracting…"
    assert window.bar["value"] == 100
    assert window.percent_label.cget("text") == "100 %"


def test_unknown_total_shows_zero(window):
    window.update("Ep1 - A", 1, 1, "download", 10, 0)
    assert window.bar["value"] == 0


def test_close_twice_is_harmless(tk_root):
    w = progress_window.ProgressWindow(tk_root)
    w.close()
    w.close()
    assert not w.window.winfo_exists()


def test_texts_follow_language(tk_root):
    i18n.set_language("fr")
    w = progress_window.ProgressWindow(tk_root)
    try:
        w.update("Ep1 - A", 1, 1, "extract", 1, 2)
        assert w.phase_label.cget("text") == "Décompression…"
    finally:
        w.close()
