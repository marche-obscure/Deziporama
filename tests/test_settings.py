import tkinter as tk

import pytest

import settings_dialog


@pytest.fixture(scope="module")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def values(tmp_path):
    (tmp_path / "wf" / "Salon").mkdir(parents=True)
    (tmp_path / "wf" / ".hidden").mkdir()
    (tmp_path / "wf" / "Pixaroma" / "2025").mkdir(parents=True)
    (tmp_path / "dl").mkdir()
    return {"watch_dir": str(tmp_path / "dl"), "workflows_root": str(tmp_path / "wf"),
            "subfolder": "", "pixaroma_dir": str(tmp_path / "wf" / "Pixaroma"),
            "pixaroma_subfolder": ""}


@pytest.fixture
def make(tk_root):
    dialogs, saved = [], []

    def build(values, running=False):
        d = settings_dialog.SettingsDialog(tk_root, values, running, saved.append)
        dialogs.append(d)
        return d

    build.saved = saved
    yield build
    for d in dialogs:
        if d.window.winfo_exists():
            d.window.destroy()


def test_shows_current_values(make, values):
    d = make(values)
    assert d.watch_var.get() == values["watch_dir"]
    assert d.root_var.get() == values["workflows_root"]
    assert d.sub_var.get() == "(root)"
    assert d.pixaroma_var.get() == values["pixaroma_dir"]


def test_subfolder_choices(make, values):
    d = make(values)
    assert d.subfolder_choices() == ["(root)", "Pixaroma", "Salon"]
    assert d.pixaroma_subfolder_choices() == ["(root)", "2025"]


def test_ok_saves_values(make, values, tmp_path):
    d = make(values)
    d.sub_var.set("Salon")
    d.pixaroma_var.set(str(tmp_path / "Pix"))
    d.ok()
    assert make.saved == [dict(values, subfolder="Salon", pixaroma_dir=str(tmp_path / "Pix"))]
    assert not d.window.winfo_exists()


def test_root_label_saved_as_empty_subfolder(make, values):
    values["subfolder"] = "Salon"
    d = make(values)
    d.sub_var.set("(root)")
    d.ok()
    assert make.saved[0]["subfolder"] == ""


def test_cancel_saves_nothing(make, values):
    d = make(values)
    d.sub_var.set("Salon")
    d.cancel()
    assert make.saved == []
    assert not d.window.winfo_exists()


def test_running_locks_watched_and_workflows_folders(make, values):
    d = make(values, running=True)
    for widget in (d.watch_entry, d.watch_btn, d.root_entry, d.root_btn):
        assert str(widget.cget("state")) == "disabled"
    assert str(d.pixaroma_entry.cget("state")) == "normal"
    assert str(d.sub_combo.cget("state")) == "readonly"


def test_create_subfolder(make, values, tmp_path):
    d = make(values)
    assert d.create_subfolder("  Nouveau  ") is None
    assert (tmp_path / "wf" / "Nouveau").is_dir()
    assert d.sub_var.get() == "Nouveau"
    assert "Nouveau" in d.subfolder_choices()


def test_create_subfolder_rejects_invalid_name(make, values, tmp_path):
    d = make(values)
    assert d.create_subfolder("..") is not None
    assert d.create_subfolder("a/b") is not None
    assert not (tmp_path / "a").exists()


def test_texts_follow_language(make, values):
    import i18n
    i18n.set_language("de")
    d = make(values)
    assert d.window.title() == "Einstellungen"
    assert d.sub_var.get() == "(Stammordner)"


def test_pixaroma_subfolder_saved(make, values):
    d = make(values)
    assert d.pixaroma_sub_var.get() == "(root)"
    d.pixaroma_sub_var.set("2025")
    d.ok()
    assert make.saved[0]["pixaroma_subfolder"] == "2025"


def test_create_pixaroma_subfolder(make, values, tmp_path):
    d = make(values)
    assert d.create_subfolder("2026", pixaroma=True) is None
    assert (tmp_path / "wf" / "Pixaroma" / "2026").is_dir()
    assert d.pixaroma_sub_var.get() == "2026"
    assert d.sub_var.get() == "(root)"
