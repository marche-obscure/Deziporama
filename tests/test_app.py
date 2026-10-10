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


class FakeShortcut:
    """Par défaut le raccourci existe : aucune question ne s'ouvre dans les autres tests."""

    def __init__(self):
        self.present, self.fail, self.created = True, False, 0

    def exists(self):
        return self.present

    def create(self):
        if self.fail:
            raise OSError("bureau inaccessible")
        self.created += 1
        self.present = True
        return "C:/Bureau/Deziporama.lnk"


@pytest.fixture
def fake_shortcut(monkeypatch):
    fake = FakeShortcut()
    monkeypatch.setattr(app, "shortcut", fake)
    return fake


@pytest.fixture
def saved(monkeypatch):
    configs = []
    monkeypatch.setattr(app, "save_config", lambda cfg, path=None: configs.append(dict(cfg)))
    return configs


@pytest.fixture
def fakes(monkeypatch, fake_shortcut, saved):
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


@pytest.mark.parametrize("hidden_parent", [False, True])
def test_dialogs_centered_on_screen(tk_root, hidden_parent):
    top = tk.Toplevel(tk_root)
    if hidden_parent:
        top.withdraw()
    measured = []

    def measure_then_click():
        d = [w for w in top.winfo_children() if isinstance(w, tk.Toplevel)][0]
        d.update_idletasks()
        cx = d.winfo_rootx() + d.winfo_width() // 2
        cy = d.winfo_rooty() + d.winfo_height() // 2
        measured.append((cx, cy, d.winfo_screenwidth() // 2, d.winfo_screenheight() // 2))
        _click_in_dialog(top, "Annuler")

    try:
        top.after(500, measure_then_click)
        app.ask_already_running(top)
        cx, cy, sx, sy = measured[0]
        assert abs(cx - sx) <= 40, measured
        assert abs(cy - sy) <= 60, measured
    finally:
        top.destroy()


def test_application_name(window):
    assert window.root.title() == "Deziporama"
    assert window.tray.tooltip.startswith("Deziporama — surveillance")


def test_already_running_message_uses_name(tk_root):
    top = tk.Toplevel(tk_root)
    texts = []

    def read_then_cancel():
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        dialogs = [w for w in top.winfo_children() if isinstance(w, tk.Toplevel)]
        texts.extend(w.cget("text") for d in dialogs for w in descendants(d) if w.winfo_class() == "TLabel")
        texts.extend(d.title() for d in dialogs)
        _click_in_dialog(top, "Annuler")

    try:
        top.after(300, read_then_cancel)
        app.ask_already_running(top)
        assert any(t.startswith("Deziporama est déjà lancé") for t in texts), texts
        assert "Deziporama" in texts
    finally:
        top.destroy()


# --- Logo -------------------------------------------------------------------------

def test_window_shows_banner_and_icon(window):
    assert window.banner_label is not None
    assert window.banner_label.cget("image")
    assert window.icon_images  # icône de la barre de titre / barre des tâches


def test_window_without_logo_still_opens(tk_root, fakes, tmp_path, monkeypatch):
    import logo
    monkeypatch.setattr(logo, "LOGO_PATH", tmp_path / "absent.webp")
    top = tk.Toplevel(tk_root)
    a = app.App(top)
    try:
        assert a.banner_label is None
        assert a.icon_images == []
    finally:
        a._quit()


# --- Raccourci bureau -------------------------------------------------------------

def pump(root, seconds=0.6):
    import time
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


@pytest.fixture
def fresh_window(tk_root, fakes, fake_shortcut, monkeypatch):
    """Fabrique une fenêtre ; la réponse à la question du raccourci est simulée."""
    answers, windows = [], []

    def ask(*args, **kwargs):
        answers.append(args[1] if len(args) > 1 else kwargs.get("title"))
        return ask.reply

    ask.reply = True
    monkeypatch.setattr(app, "choice_dialog", ask)

    def make(**kwargs):
        top = tk.Toplevel(tk_root)
        a = app.App(top, **kwargs)
        windows.append(a)
        pump(top)
        return a

    make.answers = answers
    make.ask = ask
    yield make
    for a in windows:
        if a.root.winfo_exists():
            a._quit()


def test_first_launch_offers_shortcut_and_creates_it(fresh_window, fake_shortcut, saved):
    fake_shortcut.present = False
    a = fresh_window()
    assert len(fresh_window.answers) == 1
    assert fake_shortcut.created == 1
    assert saved[-1]["desktop_shortcut_asked"] is True
    assert str(a.shortcut_btn["state"]) == "disabled"


def test_declining_marks_asked_without_creating(fresh_window, fake_shortcut, saved):
    fake_shortcut.present = False
    fresh_window.ask.reply = False
    a = fresh_window()
    assert fake_shortcut.created == 0
    assert saved[-1]["desktop_shortcut_asked"] is True
    assert str(a.shortcut_btn["state"]) == "normal"


def test_not_offered_when_already_asked(fresh_window, fake_shortcut, monkeypatch):
    fake_shortcut.present = False
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(app.DEFAULTS, desktop_shortcut_asked=True))
    fresh_window()
    assert fresh_window.answers == []


def test_not_offered_when_shortcut_exists(fresh_window):
    fresh_window()
    assert fresh_window.answers == []


def test_not_offered_at_login(fresh_window, fake_shortcut):
    fake_shortcut.present = False
    fresh_window(at_login=True)
    assert fresh_window.answers == []


def test_shortcut_button_creates_and_disables(window, fake_shortcut):
    fake_shortcut.present = False
    window._update_shortcut_button()
    assert str(window.shortcut_btn["state"]) == "normal"
    window.shortcut_btn.invoke()
    assert fake_shortcut.created == 1
    assert str(window.shortcut_btn["state"]) == "disabled"
    assert "Raccourci créé" in window.log.get("1.0", "end")


def test_shortcut_button_reenabled_when_shortcut_deleted(window, fake_shortcut):
    assert str(window.shortcut_btn["state"]) == "disabled"
    fake_shortcut.present = False
    window._check_health()
    assert str(window.shortcut_btn["state"]) == "normal"


def test_shortcut_creation_failure_logged(window, fake_shortcut):
    fake_shortcut.present = False
    fake_shortcut.fail = True
    window._update_shortcut_button()
    window.shortcut_btn.invoke()
    assert "bureau inaccessible" in window.log.get("1.0", "end")
    assert str(window.shortcut_btn["state"]) == "normal"


def test_save_keeps_shortcut_flag(window, saved):
    window.cfg["desktop_shortcut_asked"] = True
    window.sub_var.set("Salon")
    assert saved[-1]["desktop_shortcut_asked"] is True
