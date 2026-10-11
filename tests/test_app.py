import threading
import tkinter as tk

import pytest

import app


@pytest.fixture(scope="module")
def tk_root():
    # One Tk interpreter per module: creating several sometimes fails on Windows.
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

    def refresh_menu(self):
        self.menu_refreshed = getattr(self, "menu_refreshed", 0) + 1

    def stop(self):
        self.stopped = True


class FakeAutostart:
    STARTUP_FLAG = "--at-login"
    LEGACY_FLAGS = ("--demarrage",)

    def __init__(self, enabled=False, fail=False):
        self.enabled, self.fail, self.calls = enabled, fail, []

    def is_enabled(self):
        return self.enabled

    def enable(self):
        if self.fail:
            raise OSError("access denied")
        self.calls.append("enable")
        self.enabled = True

    def disable(self):
        self.calls.append("disable")
        self.enabled = False


class FakeShortcut:
    """By default the shortcut exists, so no question pops up in the other tests."""

    def __init__(self):
        self.present, self.fail, self.created = True, False, 0

    def exists(self):
        return self.present

    def create(self):
        if self.fail:
            raise OSError("desktop unreachable")
        self.created += 1
        self.present = True
        return "C:/Desktop/Deziporama.lnk"


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
    # Language already chosen: no first-launch dialog can block the tests.
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(app.DEFAULTS, language="en"))
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
        a._quit()  # stops watching and cancels scheduled callbacks


def test_dest_readable_from_worker_thread(window, tmp_path):
    """The watcher thread reads the destination: it must never touch Tkinter."""
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
    window.sub_var.set("(root)")
    assert window._dest() == tmp_path


# --- Start at Windows sign-in --------------------------------------------------

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
    assert "access denied" in window.log.get("1.0", "end")


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


# --- Minimize to the notification area -------------------------------------------

def test_minimize_hides_window_and_shows_tray(window):
    window.root.update()
    window.root.iconify()
    window.root.update()
    assert window.root.state() == "withdrawn"
    assert window.tray.visible


def test_tray_show_command_restores_window(window):
    window._hide_to_tray()
    t = threading.Thread(target=window.tray.on_show)  # called from the pystray thread
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
    """The dialog offers the three choices and returns the one clicked."""
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
        for d in dialogs:  # button not found: close the dialog so the test fails instead of hanging
            d.destroy()

    for label, expected in [("Minimize to tray", "minimize"), ("Quit", "quit"), ("Cancel", "")]:
        window.root.after(300, lambda l=label: click(l))
        assert (window._ask_close() or "") == expected
    assert clicked == ["Minimize to tray", "Quit", "Cancel"]


def test_quit_cancels_scheduled_callbacks(window):
    mine = set(window._scheduled.values())
    assert len(mine) == 2  # _drain and _check_health are scheduled
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
    for d in dialogs:  # button not found: close the dialog so the test fails instead of hanging
        d.destroy()
    return False


@pytest.mark.parametrize("label, expected", [("Show the running one", True), ("Cancel", False)])
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
    """Second copy: the main window is hidden, the warning must still be visible."""
    top = tk.Toplevel(tk_root)
    top.withdraw()
    seen = []

    def check_then_click():
        dialogs = [w for w in top.winfo_children() if isinstance(w, tk.Toplevel)]
        seen.append(bool(dialogs) and bool(dialogs[0].winfo_viewable()))
        _click_in_dialog(top, "Cancel")

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
        _click_in_dialog(top, "Cancel")

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
    assert window.tray.tooltip.startswith("Deziporama — watching")


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
        _click_in_dialog(top, "Cancel")

    try:
        top.after(300, read_then_cancel)
        app.ask_already_running(top)
        assert any(t.startswith("Deziporama is already running") for t in texts), texts
        assert "Deziporama" in texts
    finally:
        top.destroy()


# --- Logo -------------------------------------------------------------------------

def test_window_shows_banner_and_icon(window):
    assert window.banner_label is not None
    assert window.banner_label.cget("image")
    assert window.icon_images  # title bar / taskbar icon


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


# --- Desktop shortcut -------------------------------------------------------------

def pump(root, seconds=0.6):
    import time
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


@pytest.fixture
def fresh_window(tk_root, fakes, fake_shortcut, monkeypatch):
    """Builds a window; the answer to the shortcut question is simulated."""
    answers, windows = [], []

    def ask(parent, title, message, buttons):
        answers.append(message)
        values = [value for _, value in buttons]
        if set(values) <= set(app.i18n.LANGUAGES):  # language question
            return ask.language
        return ask.reply

    ask.reply = True
    ask.language = "fr"
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
    monkeypatch.setattr(app, "load_config",
                        lambda path=None: dict(app.DEFAULTS, language="en", desktop_shortcut_asked=True))
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
    assert "Shortcut created" in window.log.get("1.0", "end")


def test_shortcut_not_checked_periodically(window, fake_shortcut):
    assert str(window.shortcut_btn["state"]) == "disabled"
    fake_shortcut.present = False
    window._check_health()
    assert str(window.shortcut_btn["state"]) == "disabled"


def test_shortcut_rechecked_when_window_shown(window, fake_shortcut):
    window._hide_to_tray()
    fake_shortcut.present = False
    window._show_window()
    assert str(window.shortcut_btn["state"]) == "normal"


def test_shortcut_creation_failure_logged(window, fake_shortcut):
    fake_shortcut.present = False
    fake_shortcut.fail = True
    window._update_shortcut_button()
    window.shortcut_btn.invoke()
    assert "desktop unreachable" in window.log.get("1.0", "end")
    assert str(window.shortcut_btn["state"]) == "normal"


def test_save_keeps_shortcut_flag(window, saved):
    window.cfg["desktop_shortcut_asked"] = True
    window.sub_var.set("Salon")
    assert saved[-1]["desktop_shortcut_asked"] is True


# --- Startup flag renamed to English ------------------------------------------

def test_login_flag_is_english_and_legacy_flag_still_works():
    assert app.autostart.STARTUP_FLAG == "--at-login"
    assert app.is_login_start(["app.py", "--at-login"])
    assert app.is_login_start(["app.py", "--demarrage"])  # entry written by older versions


def test_enabled_autostart_command_is_refreshed(tk_root, fakes):
    fakes.enabled = True
    top = tk.Toplevel(tk_root)
    a = app.App(top)
    try:
        assert fakes.calls == ["enable"]  # rewrites the Run entry with the current command
    finally:
        a._quit()


def test_disabled_autostart_is_left_alone(window, fakes):
    assert fakes.calls == []


# --- Languages --------------------------------------------------------------------

def test_language_selector_in_banner(window):
    assert list(window.language_menu_values) == ["English", "Français", "Deutsch"]
    assert window.language_var.get() == "English"


def test_switching_language_retranslates_window(window, saved):
    window.language_var.set("Français")
    assert window.toggle_btn.cget("text") == "Démarrer"
    assert window.retry_btn.cget("text") == "Réessayer les erreurs"
    assert window.shortcut_btn.cget("text") == "Créer le raccourci bureau"
    assert window.tray.tooltip == "Deziporama — surveillance arrêtée"
    assert window.tray.menu_refreshed >= 1
    assert saved[-1]["language"] == "fr"
    window.language_var.set("Deutsch")
    assert window.toggle_btn.cget("text") == "Starten"


def test_switching_language_keeps_root_subfolder(window, tmp_path):
    window.sub_var.set("(root)")
    window.language_var.set("Français")
    assert window.sub_var.get() == "(racine)"
    assert window._dest() == tmp_path
    assert window.dest_label.cget("text") == f"Destination Workflows : {tmp_path}"


def test_first_launch_asks_language_then_shortcut(fresh_window, fake_shortcut, saved, monkeypatch):
    fake_shortcut.present = False
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(app.DEFAULTS))
    a = fresh_window()
    assert fresh_window.answers[0] == app.i18n.LANGUAGE_PROMPT
    assert fresh_window.answers[1] == "Créer un raccourci Deziporama sur le bureau ?"  # asked in French
    assert saved[-1]["language"] == "fr"
    assert a.toggle_btn.cget("text") == "Démarrer"


def test_closing_language_dialog_keeps_windows_language(fresh_window, saved, monkeypatch):
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(app.DEFAULTS))
    monkeypatch.setattr(app.i18n, "system_language", lambda: "de")
    fresh_window.ask.language = None
    a = fresh_window()
    assert saved[-1]["language"] == "de"
    assert a.toggle_btn.cget("text") == "Starten"


def test_language_asked_only_once(fresh_window):
    fresh_window()  # language "en" already saved by the fakes
    assert app.i18n.LANGUAGE_PROMPT not in fresh_window.answers


def test_language_not_asked_at_login(fresh_window, monkeypatch):
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(app.DEFAULTS))
    fresh_window(at_login=True)
    assert fresh_window.answers == []


def test_windows_language_used_until_chosen(monkeypatch):
    monkeypatch.setattr(app.i18n, "system_language", lambda: "de")
    app.init_language(dict(app.DEFAULTS))
    assert app.i18n.get_language() == "de"
    app.init_language(dict(app.DEFAULTS, language="fr"))
    assert app.i18n.get_language() == "fr"


def test_already_running_dialog_in_current_language(tk_root):
    app.i18n.set_language("de")
    top = tk.Toplevel(tk_root)
    texts = []

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    def read_then_cancel():
        dialogs = [w for w in top.winfo_children() if isinstance(w, tk.Toplevel)]
        texts.extend(w.cget("text") for d in dialogs for w in descendants(d)
                     if w.winfo_class() in ("TLabel", "TButton"))
        _click_in_dialog(top, "Abbrechen")

    try:
        top.after(300, read_then_cancel)
        assert app.ask_already_running(top) is False
        assert any(x.startswith("Deziporama läuft bereits") for x in texts), texts
        assert "Laufendes Fenster anzeigen" in texts
    finally:
        top.destroy()


# --- Settings (gear icon) ---------------------------------------------------------

def test_gear_button_in_banner(window):
    assert window.settings_btn.cget("text") == "⚙"


def test_summary_shows_destination_and_pixaroma_folder(window, tmp_path):
    assert window.dest_label.cget("text") == f"Workflows destination: {tmp_path}"
    assert window.pixaroma_label.cget("text") == "Pixaroma workflows destination: —"


def test_apply_settings_updates_and_saves(window, saved, tmp_path):
    (tmp_path / "dl").mkdir()
    window._apply_settings({"watch_dir": str(tmp_path / "dl"), "workflows_root": str(tmp_path),
                            "subfolder": "Salon", "pixaroma_dir": str(tmp_path / "Pix"),
                            "pixaroma_subfolder": "2026"})
    assert window._dest() == tmp_path / "Salon"
    assert window.dest_label.cget("text") == f"Workflows destination: {tmp_path / 'Salon'}"
    assert window.pixaroma_label.cget("text") == f"Pixaroma workflows destination: {tmp_path / 'Pix' / '2026'}"
    assert saved[-1]["pixaroma_subfolder"] == "2026"
    assert saved[-1]["subfolder"] == "Salon"
    assert saved[-1]["pixaroma_dir"] == str(tmp_path / "Pix")
    assert saved[-1]["watch_dir"] == str(tmp_path / "dl")


def test_open_settings_passes_current_values(window, monkeypatch, tmp_path):
    opened = []

    class FakeDialog:
        def __init__(self, parent, values, running, on_save, on_stop=None):
            opened.append((values, running))
            self.on_save = on_save

        def run_modal(self):
            self.on_save(dict(opened[0][0], subfolder="Salon"))

    monkeypatch.setattr(app, "SettingsDialog", FakeDialog)
    window._open_settings()
    values, running = opened[0]
    assert values["workflows_root"] == str(tmp_path)
    assert running is False
    assert window.cfg["subfolder"] == "Salon"


def test_pixaroma_check_checkbox_saved(window, saved):
    window.pixaroma_check_var.set(True)
    assert saved[-1]["pixaroma_check_at_start"] is True


# --- Pixaroma ---------------------------------------------------------------------

class FakePixaromaWindow:
    instances = []

    def __init__(self, parent, pixaroma_dir, last_seen, **callbacks):
        self.pixaroma_dir, self.last_seen, self.callbacks = pixaroma_dir, last_seen, callbacks
        self.window = tk.Toplevel(parent)
        FakePixaromaWindow.instances.append(self)


@pytest.fixture
def fake_pixaroma_window(monkeypatch):
    FakePixaromaWindow.instances = []
    monkeypatch.setattr(app, "PixaromaWindow", FakePixaromaWindow)
    return FakePixaromaWindow


def test_pixaroma_button(window):
    assert window.pixaroma_btn.cget("text") == "Pixaroma"


def test_pixaroma_without_folder_logs_error(window, fake_pixaroma_window):
    window._open_pixaroma()
    assert fake_pixaroma_window.instances == []
    assert "choose the Pixaroma folder" in window.log.get("1.0", "end")


def test_pixaroma_window_opened_once_and_wired(window, fake_pixaroma_window, saved, tmp_path):
    window.pixaroma_var.set(str(tmp_path / "Pix"))
    window.cfg["pixaroma_last_seen"] = 7
    window._open_pixaroma()
    window._open_pixaroma()  # already open: brought to front, not duplicated
    assert len(fake_pixaroma_window.instances) == 1
    w = fake_pixaroma_window.instances[0]
    assert w.pixaroma_dir == tmp_path / "Pix" and w.last_seen == 7
    assert w.callbacks["scan_dir"] == tmp_path / "Pix"
    w.callbacks["on_seen"](12)
    assert saved[-1]["pixaroma_last_seen"] == 12
    w.callbacks["on_message"]("Downloading Ep12…", "ignored")
    w.callbacks["on_result"](app.ImportResult("imported", tmp_path / "Ep12.zip", tmp_path / "Pix" / "Ep12 - X"))
    window._drain()
    log = window.log.get("1.0", "end")
    assert "Downloading Ep12…" in log and "Imported: Ep12.zip" in log


def test_last_seen_never_goes_back(window, fake_pixaroma_window, tmp_path):
    window.pixaroma_var.set(str(tmp_path))
    window.cfg["pixaroma_last_seen"] = 20
    window._open_pixaroma()
    fake_pixaroma_window.instances[0].callbacks["on_seen"](12)
    assert window.cfg["pixaroma_last_seen"] == 20


def _episodes(*numbers):
    from tests.test_pixaroma import episode_data, episodes_js
    return app.pixaroma.parse_episodes(episodes_js(*(episode_data(n) for n in numbers)))


def test_startup_check_reports_new_episodes(tk_root, fakes, monkeypatch):
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(
        app.DEFAULTS, language="en", pixaroma_check_at_start=True, pixaroma_last_seen=3))
    monkeypatch.setattr(app.pixaroma, "fetch_episodes", lambda: _episodes(1, 2, 3, 4, 5))
    monkeypatch.setattr(app.App, "_run_background", lambda self, fn: fn())
    top = tk.Toplevel(tk_root)
    a = app.App(top)
    try:
        a._drain()
        assert "2 new Pixaroma episode(s): 5, 4" in a.log.get("1.0", "end")
        assert a.cfg["pixaroma_last_seen"] == 3  # still "new" until the list is opened
    finally:
        a._quit()


def test_startup_check_up_to_date(tk_root, fakes, monkeypatch):
    monkeypatch.setattr(app, "load_config", lambda path=None: dict(
        app.DEFAULTS, language="en", pixaroma_check_at_start=True, pixaroma_last_seen=5))
    monkeypatch.setattr(app.pixaroma, "fetch_episodes", lambda: _episodes(4, 5))
    monkeypatch.setattr(app.App, "_run_background", lambda self, fn: fn())
    top = tk.Toplevel(tk_root)
    a = app.App(top)
    try:
        a._drain()
        assert "Pixaroma: no new episode." in a.log.get("1.0", "end")
    finally:
        a._quit()


def test_startup_check_off_by_default(window, monkeypatch):
    called = []
    monkeypatch.setattr(app.pixaroma, "fetch_episodes", lambda: called.append(1) or [])
    window._drain()
    assert called == []


def test_pixaroma_subfolder_is_the_import_destination(window, fake_pixaroma_window, tmp_path):
    window._apply_settings({"watch_dir": window.watch_var.get(), "workflows_root": str(tmp_path),
                            "subfolder": "", "pixaroma_dir": str(tmp_path / "Pix"),
                            "pixaroma_subfolder": "2026"})
    window._open_pixaroma()
    w = fake_pixaroma_window.instances[0]
    assert w.pixaroma_dir == tmp_path / "Pix" / "2026"  # where episodes are imported
    assert w.callbacks["scan_dir"] == tmp_path / "Pix"  # where imported episodes are looked for


def test_gear_is_brightly_colored(window):
    assert window.settings_btn.cget("foreground") == app.GEAR_COLOR


def test_settings_can_stop_watching(window, monkeypatch, tmp_path):
    (tmp_path / "dl").mkdir()
    window.watch_var.set(str(tmp_path / "dl"))
    window._toggle()
    assert window.watcher.running
    received = []

    class FakeDialog:
        def __init__(self, parent, values, running, on_save, on_stop=None):
            received.append(running)
            self.on_stop = on_stop

        def run_modal(self):
            self.on_stop()

    monkeypatch.setattr(app, "SettingsDialog", FakeDialog)
    window._open_settings()
    assert received == [True]
    assert not window.watcher.running
    assert window.toggle_btn.cget("text") == "Start"
