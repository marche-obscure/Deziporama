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


class FakeTray:
    def __init__(self, on_show, on_quit):
        self.on_show, self.on_quit = on_show, on_quit
        self.visible = False
        self.stopped = False
        self.tooltip = ""

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def set_tooltip(self, text):
        self.tooltip = text

    def stop(self):
        self.stopped = True


class FakeAutostart:
    STARTUP_FLAG = "--demarrage"

    def __init__(self, enabled=False, fail=False):
        self.enabled, self.fail, self.calls = enabled, fail, []

    def is_enabled(self):
        return self.enabled

    def enable(self):
        if self.fail:
            raise OSError("accès refusé")
        self.calls.append("enable")
        self.enabled = True

    def disable(self):
        self.calls.append("disable")
        self.enabled = False


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(app, "save_config", lambda cfg, path=None: None)
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(app.DEFAULTS))
    monkeypatch.setattr(app, "TrayIcon", FakeTray)
    fake_autostart = FakeAutostart()
    monkeypatch.setattr(app, "autostart", fake_autostart)
    return fake_autostart


@pytest.fixture
def window(tk_root, fakes, tmp_path):
    top = tk.Toplevel(tk_root)
    a = app.App(top)
    a.root_var.set(str(tmp_path))
    yield a
    if top.winfo_exists():
        a._quit()  # arrête la surveillance et annule les tâches programmées


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


# --- Lancement à l'ouverture de session ----------------------------------------

def test_autostart_checkbox_reflects_registry(tk_root, fakes):
    fakes.enabled = True
    top = tk.Toplevel(tk_root)
    try:
        assert app.App(top).autostart_var.get() is True
    finally:
        top.destroy()


def test_autostart_checkbox_enables_and_disables(window, fakes):
    window.autostart_var.set(True)
    window.autostart_var.set(False)
    assert fakes.calls == ["enable", "disable"]


def test_autostart_failure_reverts_checkbox(window, fakes):
    fakes.fail = True
    window.autostart_var.set(True)
    assert window.autostart_var.get() is False
    assert "accès refusé" in window.log.get("1.0", "end")


def test_started_at_login_hides_and_starts_watching(tk_root, fakes, tmp_path, monkeypatch):
    (tmp_path / "dl").mkdir()
    (tmp_path / "wf").mkdir()
    cfg = dict(app.DEFAULTS, watch_dir=str(tmp_path / "dl"), workflows_root=str(tmp_path / "wf"))
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(cfg))
    top = tk.Toplevel(tk_root)
    a = app.App(top, at_login=True)
    try:
        top.update()
        assert top.state() == "withdrawn"
        assert a.tray.visible
        assert a.watcher is not None and a.watcher.running
        assert "active" in a.tray.tooltip
    finally:
        a.watcher.stop()
        top.destroy()


def test_is_login_start():
    assert app.is_login_start(["app.py", "--demarrage"])
    assert not app.is_login_start(["app.py"])


# --- Réduction près de l'horloge -------------------------------------------------

def test_minimize_hides_window_and_shows_tray(window):
    window.root.update()
    window.root.iconify()
    window.root.update()
    assert window.root.state() == "withdrawn"
    assert window.tray.visible


def test_tray_show_command_restores_window(window):
    window._hide_to_tray()
    t = threading.Thread(target=window.tray.on_show)  # appelé depuis le thread de pystray
    t.start()
    t.join()
    window._drain()
    window.root.update()
    assert window.root.state() == "normal"
    assert not window.tray.visible


def test_tray_quit_command_quits(window):
    window.tray.on_quit()
    window._drain()
    assert not window.root.winfo_exists()
    assert window.tray.stopped


# --- Bouton Fermer ----------------------------------------------------------------

def test_close_then_minimize(window, monkeypatch):
    monkeypatch.setattr(window, "_ask_close", lambda: "minimize")
    window._close()
    assert window.root.state() == "withdrawn"
    assert window.tray.visible


def test_close_then_quit(window, monkeypatch):
    monkeypatch.setattr(window, "_ask_close", lambda: "quit")
    window._close()
    assert not window.root.winfo_exists()
    assert window.tray.stopped


def test_close_then_cancel(window, monkeypatch):
    monkeypatch.setattr(window, "_ask_close", lambda: None)
    window._close()
    assert window.root.winfo_exists()
    assert window.root.state() == "normal"
    assert not window.tray.visible


def test_close_dialog_buttons(window):
    """La boîte de dialogue propose les trois choix et renvoie celui cliqué."""
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    clicked = []

    def click(label):
        dialogs = [w for w in window.root.winfo_children() if isinstance(w, tk.Toplevel)]
        for b in (b for d in dialogs for b in descendants(d)):
            if b.winfo_class() == "TButton" and b.cget("text") == label:
                clicked.append(label)
                b.invoke()
                return
        for d in dialogs:  # bouton introuvable : on ferme pour faire échouer le test sans bloquer
            d.destroy()

    for label, expected in [("Réduire près de l'horloge", "minimize"), ("Quitter", "quit"), ("Annuler", "")]:
        window.root.after(300, lambda l=label: click(l))
        assert (window._ask_close() or "") == expected
    assert clicked == ["Réduire près de l'horloge", "Quitter", "Annuler"]


def test_quit_cancels_scheduled_callbacks(window):
    mine = set(window._scheduled.values())
    assert len(mine) == 2  # _drain et _check_health sont programmés
    assert mine <= set(window.root.tk.call("after", "info"))
    window._quit()
    assert not set(window.root.tk.call("after", "info")) & mine


# --- Double lancement ---------------------------------------------------------

def _click_in_dialog(parent, label):
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    dialogs = [w for w in parent.winfo_children() if isinstance(w, tk.Toplevel)]
    for b in (b for d in dialogs for b in descendants(d)):
        if b.winfo_class() == "TButton" and b.cget("text") == label:
            b.invoke()
            return True
    for d in dialogs:  # bouton introuvable : on ferme pour faire échouer le test sans bloquer
        d.destroy()
    return False


@pytest.mark.parametrize("label, expected", [("Afficher celui déjà lancé", True), ("Annuler", False)])
def test_already_running_dialog(tk_root, label, expected):
    top = tk.Toplevel(tk_root)
    try:
        clicked = []
        top.after(300, lambda: clicked.append(_click_in_dialog(top, label)))
        assert app.ask_already_running(top) is expected
        assert clicked == [True]
    finally:
        top.destroy()


def test_already_running_dialog_visible_with_hidden_parent(tk_root):
    """Deuxième copie : la fenêtre principale est cachée, l'avertissement doit rester visible."""
    top = tk.Toplevel(tk_root)
    top.withdraw()
    seen = []

    def check_then_click():
        dialogs = [w for w in top.winfo_children() if isinstance(w, tk.Toplevel)]
        seen.append(bool(dialogs) and bool(dialogs[0].winfo_viewable()))
        _click_in_dialog(top, "Annuler")

    try:
        top.after(500, check_then_click)
        app.ask_already_running(top)
        assert seen == [True]
    finally:
        top.destroy()
