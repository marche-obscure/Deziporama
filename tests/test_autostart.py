import winreg

import pytest

import autostart

TEST_KEY = r"Software\ImporteurWorkflowsComfyUI-Tests\Run"


@pytest.fixture
def key():
    """Test registry key (never the real Windows Run key)."""
    yield TEST_KEY
    for path in (TEST_KEY, r"Software\ImporteurWorkflowsComfyUI-Tests"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass


def test_disabled_by_default(key):
    assert not autostart.is_enabled(key)


def test_enable_then_disable(key):
    autostart.enable('"C:\\x\\pythonw.exe" "C:\\x\\app.py" --demarrage', key)
    assert autostart.is_enabled(key)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
        value, _ = winreg.QueryValueEx(k, autostart.VALUE_NAME)
    assert value == '"C:\\x\\pythonw.exe" "C:\\x\\app.py" --demarrage'
    autostart.disable(key)
    assert not autostart.is_enabled(key)


def test_disable_when_absent_is_noop(key):
    autostart.disable(key)
    assert not autostart.is_enabled(key)


def test_startup_command_uses_pythonw_and_flag():
    cmd = autostart.startup_command()
    assert "pythonw.exe" in cmd.lower()
    assert cmd.endswith(f'"{autostart.APP_PATH}" {autostart.STARTUP_FLAG}')


def test_real_run_key_is_the_windows_one():
    assert autostart.RUN_KEY == r"Software\Microsoft\Windows\CurrentVersion\Run"
