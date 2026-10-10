import threading
import tkinter as tk

import pytest

import app


@pytest.fixture(scope="module")
def tk_root():
    # Un seul interpréteur Tk par module : en créer plusieurs échoue parfois sous Windows.
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def window(tk_root, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "save_config", lambda cfg, path=None: None)
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(app.DEFAULTS))
    top = tk.Toplevel(tk_root)
    a = app.App(top)
    a.root_var.set(str(tmp_path))
    yield a
    top.destroy()


def test_dest_readable_from_worker_thread(window, tmp_path):
    """Le thread de surveillance lit la destination : il ne doit pas toucher Tkinter."""
    window.sub_var.set("Salon")
    out = {}

    def worker():
        try:
            out["dest"] = window._dest()
        except Exception as e:  # noqa: BLE001
            out["error"] = e

    t = threading.Thread(target=worker)
    t.start()
    t.join(5)
    assert "error" not in out, out.get("error")
    assert out["dest"] == tmp_path / "Salon"


def test_root_label_means_workflows_root(window, tmp_path):
    window.sub_var.set(app.ROOT_LABEL)
    assert window._dest() == tmp_path
