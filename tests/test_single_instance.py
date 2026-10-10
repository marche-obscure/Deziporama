import threading
import uuid

import pytest

import single_instance


@pytest.fixture
def name():
    # Unique name per test: never interferes with a really running app.
    return f"ImporteurWorkflowsComfyUI-Test-{uuid.uuid4().hex}"


def test_first_acquire_wins_second_loses(name):
    first = single_instance.SingleInstance(name)
    second = single_instance.SingleInstance(name)
    try:
        assert first.acquire()
        assert not second.acquire()
    finally:
        second.close()
        first.close()


def test_released_after_close(name):
    first = single_instance.SingleInstance(name)
    assert first.acquire()
    first.close()
    again = single_instance.SingleInstance(name)
    try:
        assert again.acquire()
    finally:
        again.close()


def test_signal_show_reaches_listener(name):
    shown = threading.Event()
    listener = single_instance.listen_show(name, shown.set)
    try:
        assert single_instance.signal_show(name)
        assert shown.wait(3)
    finally:
        listener.stop()


def test_signal_show_without_listener_returns_false(name):
    assert not single_instance.signal_show(name)


def test_listener_stops_quickly(name):
    listener = single_instance.listen_show(name, lambda: None)
    listener.stop()
    assert not listener.is_alive()
