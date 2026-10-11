import tkinter as tk

import pytest

import ui


@pytest.fixture(scope="module")
def tk_root():
    # One Tk interpreter per module: creating several sometimes fails on Windows.
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def root(tk_root):
    top = tk.Toplevel(tk_root)
    yield top
    top.destroy()


def test_app_icon_is_the_default_for_every_window(root, tmp_path, monkeypatch):
    calls = []
    real = root.iconbitmap
    monkeypatch.setattr(root, "iconbitmap", lambda *a, **k: calls.append(k) or real(*a, **k))
    ico = tmp_path / "app.ico"
    photos = ui.apply_app_icon(root, ico)
    assert ico.exists()  # generated from the logo
    assert calls == [{"default": str(ico)}]  # .ico: also used by dialogs and message boxes
    assert len(photos) == 3


def test_app_icon_without_logo(root, tmp_path, monkeypatch):
    import logo
    monkeypatch.setattr(logo, "LOGO_PATH", tmp_path / "absent.webp")
    assert ui.apply_app_icon(root, tmp_path / "app.ico") == []


def test_app_id_set(monkeypatch):
    ids = []
    monkeypatch.setattr(ui, "_set_app_id", ids.append)
    ui.set_app_id()
    assert ids == [ui.APP_ID]
