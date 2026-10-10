"""Lancement de l'applicatif à l'ouverture de session Windows (clé Run de l'utilisateur)."""

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ImporteurWorkflowsComfyUI"
APP_PATH = Path(__file__).with_name("app.py")
STARTUP_FLAG = "--demarrage"


def startup_command() -> str:
    """Commande lancée par Windows : pythonw (sans console) + app.py + drapeau de démarrage."""
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
