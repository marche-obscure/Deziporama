import subprocess

import pytest

import shortcut


def read_lnk(path):
    """Reads a .lnk shortcut through Windows (target, arguments, folder, icon)."""
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); "
              "$s.TargetPath; $s.Arguments; $s.WorkingDirectory; $s.IconLocation")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, env={**__import__("os").environ, "LNK": str(path)},
                         check=True).stdout.splitlines()
    return dict(zip(["target", "arguments", "workdir", "icon"], out))


def test_desktop_dir_exists():
    assert shortcut.desktop_dir().is_dir()


def test_absent_in_empty_folder(tmp_path):
    assert not shortcut.exists(tmp_path)


def test_create_real_shortcut(tmp_path):
    path = shortcut.create(tmp_path)
    assert path == tmp_path / "Deziporama.lnk"
    assert shortcut.exists(tmp_path)
    info = read_lnk(path)
    assert info["target"].lower().endswith("pythonw.exe")
    assert str(shortcut.APP_PATH) in info["arguments"]
    assert info["workdir"] == str(shortcut.APP_PATH.parent)
    assert info["icon"].lower().startswith(str(shortcut.ICO_PATH).lower())
    assert shortcut.ICO_PATH.exists()


def test_create_fails_cleanly(tmp_path):
    with pytest.raises(OSError):
        shortcut.create(tmp_path / "missing-folder")
