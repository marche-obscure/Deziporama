"""Une seule copie de l'applicatif à la fois (mutex nommé Windows) et signal « afficher »."""

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

INSTANCE_NAME = "ImporteurWorkflowsComfyUI"
ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.OpenEventW.restype = wintypes.HANDLE
_kernel32.SetEvent.argtypes = [wintypes.HANDLE]
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _event_name(name: str) -> str:
    # « Local\ » : propre à la session Windows de l'utilisateur.
    return f"Local\\{name}-Afficher"


class SingleInstance:
    def __init__(self, name: str = INSTANCE_NAME) -> None:
        self._name = f"Local\\{name}"
        self._handle = None

    def acquire(self) -> bool:
        """Vrai si aucune autre copie ne tourne (le mutex est alors gardé jusqu'à close())."""
        self._handle = _kernel32.CreateMutexW(None, False, self._name)
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


def signal_show(name: str = INSTANCE_NAME) -> bool:
    """Demande à la copie déjà lancée d'afficher sa fenêtre. Faux si elle n'écoute pas."""
    handle = _kernel32.OpenEventW(EVENT_MODIFY_STATE, False, _event_name(name))
    if not handle:
        return False
    try:
        return bool(_kernel32.SetEvent(handle))
    finally:
        _kernel32.CloseHandle(handle)


class _Listener(threading.Thread):
    def __init__(self, name: str, on_show: Callable[[], None]) -> None:
        super().__init__(daemon=True)
        self._handle = _kernel32.CreateEventW(None, False, False, _event_name(name))
        self._on_show = on_show
        self._stopping = threading.Event()

    def run(self) -> None:
        while not self._stopping.is_set():
            if _kernel32.WaitForSingleObject(self._handle, 200) == WAIT_OBJECT_0:
                if not self._stopping.is_set():
                    self._on_show()

    def stop(self) -> None:
        self._stopping.set()
        self.join(timeout=2)
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


def listen_show(name: str, on_show: Callable[[], None]) -> _Listener:
    """Appelle on_show (depuis un thread dédié) chaque fois qu'une autre copie le demande."""
    listener = _Listener(name, on_show)
    listener.start()
    return listener
