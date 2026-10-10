"""Start the application at Windows sign-in (the user's Run registry key)."""

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ImporteurWorkflowsComfyUI"
APP_PATH = Path(__file__).with_name("app.py")
STARTUP_FLAG = "--at-login"
LEGACY_FLAGS = ("--demarrage",)  # flag written in the Run key by older versions


def startup_command() -> str:
    """Command run by Windows: pythonw (no console) + app.py + startup flag."""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else exe}" "{APP_PATH}" {STARTUP_FLAG}'


def is_enabled(key_path: str = RUN_KEY) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def enable(command: str | None = None, key_path: str = RUN_KEY) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command or startup_command())


def disable(key_path: str = RUN_KEY) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
