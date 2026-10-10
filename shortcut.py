"""Raccourci « Deziporama » sur le bureau Windows."""

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

import logo

SHORTCUT_NAME = "Deziporama.lnk"
APP_PATH = Path(__file__).with_name("app.py")
ICO_PATH = Path(__file__).with_name("assets") / "deziporama.ico"
CSIDL_DESKTOPDIRECTORY = 0x10

# Les chemins passent par des variables d'environnement : aucun souci de guillemets ou d'accents.
_CREATE_SCRIPT = (
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:DZ_LNK); "
    "$s.TargetPath = $env:DZ_TARGET; "
    "$s.Arguments = '\"' + $env:DZ_APP + '\"'; "
    "$s.WorkingDirectory = $env:DZ_WORKDIR; "
    "if ($env:DZ_ICON) { $s.IconLocation = $env:DZ_ICON + ',0' }; "
    "$s.Description = 'Deziporama : rangement automatique des workflows ComfyUI'; "
    "$s.Save()"
)


def desktop_dir() -> Path:
    """Vrai dossier Bureau de l'utilisateur (y compris s'il est redirigé vers OneDrive)."""
    buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    if ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOPDIRECTORY, None, 0, buf) != 0:
        return Path.home() / "Desktop"
    return Path(buf.value)


def shortcut_path(desktop: Path | None = None) -> Path:
    return Path(desktop or desktop_dir()) / SHORTCUT_NAME


def exists(desktop: Path | None = None) -> bool:
    return shortcut_path(desktop).exists()


def _pythonw() -> Path:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else exe


def create(desktop: Path | None = None) -> Path:
    """Crée le raccourci ; lève OSError en cas d'échec."""
    path = shortcut_path(desktop)
    if not path.parent.is_dir():
        raise OSError(f"dossier du bureau introuvable : {path.parent}")
    has_icon = ICO_PATH.exists() or logo.write_ico(ICO_PATH)
    env = {**os.environ,
           "DZ_LNK": str(path), "DZ_TARGET": str(_pythonw()), "DZ_APP": str(APP_PATH),
           "DZ_WORKDIR": str(APP_PATH.parent), "DZ_ICON": str(ICO_PATH) if has_icon else ""}
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _CREATE_SCRIPT],
        env=env, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0 or not path.exists():
        raise OSError(result.stderr.strip() or "création du raccourci impossible")
    return path
