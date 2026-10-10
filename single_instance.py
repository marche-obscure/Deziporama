"""Only one copy of the application at a time (Windows named mutex) and a "show" signal."""

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
    # "Local" namespace: scoped to the user's Windows session.
    return f"Local\\{name}-Show"


class SingleInstance:
    def __init__(self, name: str = INSTANCE_NAME) -> None:
        self._name = f"Local\\{name}"
        self._handle = None

    def acquire(self) -> bool:
        """True if no other copy is running (the mutex is then held until close())."""
        self._handle = _kernel32.CreateMutexW(None, False, self._name)
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


def signal_show(name: str = INSTANCE_NAME) -> bool:
    """Asks the running copy to show its window. False if it is not listening."""
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
    """Calls on_show (from a dedicated thread) each time another copy asks for it."""
    listener = _Listener(name, on_show)
    listener.start()
    return listener
