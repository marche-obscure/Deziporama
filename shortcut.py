"""The "Deziporama" shortcut on the Windows desktop."""

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

import logo
from i18n import t

SHORTCUT_NAME = "Deziporama.lnk"
APP_PATH = Path(__file__).with_name("app.py")
ICO_PATH = logo.ICO_PATH
CSIDL_DESKTOPDIRECTORY = 0x10

# Paths go through environment variables: no trouble with quotes or accented characters.
_CREATE_SCRIPT = (
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:DZ_LNK); "
    "$s.TargetPath = $env:DZ_TARGET; "
    "$s.Arguments = '\"' + $env:DZ_APP + '\"'; "
    "$s.WorkingDirectory = $env:DZ_WORKDIR; "
    "if ($env:DZ_ICON) { $s.IconLocation = $env:DZ_ICON + ',0' }; "
    "$s.Description = 'Deziporama: automatic filing of ComfyUI workflows'; "
    "$s.Save()"
)


def desktop_dir() -> Path:
    """The user's real Desktop folder (including when redirected to OneDrive)."""
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
    """Creates the shortcut; raises OSError on failure."""
    path = shortcut_path(desktop)
    if not path.parent.is_dir():
        raise OSError(t("msg_desktop_missing", path=path.parent))
    has_icon = ICO_PATH.exists() or logo.write_ico(ICO_PATH)
    env = {**os.environ,
           "DZ_LNK": str(path), "DZ_TARGET": str(_pythonw()), "DZ_APP": str(APP_PATH),
           "DZ_WORKDIR": str(APP_PATH.parent), "DZ_ICON": str(ICO_PATH) if has_icon else ""}
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _CREATE_SCRIPT],
        env=env, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0 or not path.exists():
        raise OSError(result.stderr.strip() or t("msg_shortcut_failed"))
    return path
