import json
import os
import queue
import time

import pytest

import watcher
from watcher import FolderWatcher, is_candidate, wait_until_ready

UI = {"nodes": [], "links": []}


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(watcher, "READY_INTERVAL", 0.1)


@pytest.fixture
def env(tmp_path):
    watch, dest = tmp_path / "dl", tmp_path / "wf"
    watch.mkdir()
    dest.mkdir()
    results = queue.Queue()
    w = FolderWatcher(watch, lambda: dest, results.put)
    yield w, watch, dest, results
    w.stop()


def wait_result(q, timeout=10):
    return q.get(timeout=timeout)


def write_wf(path):
    path.write_text(json.dumps(UI), encoding="utf-8")


def test_is_candidate(tmp_path):
    for name in ["a.JSON", "b.zip"]:
        assert is_candidate(tmp_path / name)
    for name in ["c.crdownload", "d.tmp", "e.part", "f.png", "g.json.crdownload"]:
        assert not is_candidate(tmp_path / name)


def test_wait_until_ready_stable(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("x", encoding="utf-8")
    assert wait_until_ready(f, timeout=5, interval=0.1)


def test_wait_until_ready_missing(tmp_path):
    assert not wait_until_ready(tmp_path / "absent.json", timeout=0.5, interval=0.1)


def test_new_json_is_imported(env):
    w, watch, dest, results = env
    w.start()
    write_wf(watch / "wf.json")
    r = wait_result(results)
    assert r.status == "imported"
    assert (dest / "wf.json").exists()


def test_rename_from_crdownload_is_processed(env):
    w, watch, dest, results = env
    w.start()
    write_wf(watch / "wf.json.crdownload")
    time.sleep(0.3)
    os.rename(watch / "wf.json.crdownload", watch / "wf.json")
    r = wait_result(results)
    assert r.status == "imported"
    assert (dest / "wf.json").exists()


def test_file_processed_once(env):
    w, watch, dest, results = env
    w.start()
    f = watch / "wf.json"
    with open(f, "w", encoding="utf-8") as fh:
        fh.write('{"nodes": [],')
        fh.flush()
        fh.write(' "links": []')
        fh.flush()
        fh.write("}")
    assert wait_result(results).status == "imported"
    with pytest.raises(queue.Empty):
        results.get(timeout=3)


def test_process_existing(env):
    w, watch, dest, results = env
    write_wf(watch / "wf.json")
    w.start(process_existing=True)
    assert wait_result(results).status == "imported"


def test_existing_not_processed_by_default(env):
    w, watch, dest, results = env
    write_wf(watch / "wf.json")
    w.start()
    with pytest.raises(queue.Empty):
        results.get(timeout=2)
    assert (watch / "wf.json").exists()


def test_get_dest_read_per_file(tmp_path):
    watch = tmp_path / "dl"
    watch.mkdir()
    current = {"dest": tmp_path / "a"}
    results = queue.Queue()
    w = FolderWatcher(watch, lambda: current["dest"], results.put)
    try:
        w.start()
        write_wf(watch / "un.json")
        assert wait_result(results).target == tmp_path / "a" / "un.json"
        current["dest"] = tmp_path / "b"
        write_wf(watch / "deux.json")
        assert wait_result(results).target == tmp_path / "b" / "deux.json"
    finally:
        w.stop()


def test_stop(env):
    w, watch, dest, results = env
    w.start()
    assert w.running
    w.stop()
    assert not w.running
    write_wf(watch / "wf.json")
    with pytest.raises(queue.Empty):
        results.get(timeout=2)


def test_stop_does_not_wait_for_queued_files(tmp_path, monkeypatch):
    watch = tmp_path / "dl"
    watch.mkdir()
    for i in range(5):
        write_wf(watch / f"wf{i}.json")

    def slow_import(path, dest):
        time.sleep(1)
        return watcher.ImportResult("imported", path, dest)

    monkeypatch.setattr(watcher, "import_file", slow_import)
    results = queue.Queue()
    w = FolderWatcher(watch, lambda: tmp_path / "wf", results.put)
    w.start(process_existing=True)
    time.sleep(0.5)
    t0 = time.monotonic()
    w.stop()
    assert time.monotonic() - t0 < 1.5
    assert not w.running
    time.sleep(1.5)
    assert results.qsize() <= 1


def test_empty_placeholder_not_reported(env):
    """Firefox first creates an empty file, then renames the .part file onto it."""
    w, watch, dest, results = env
    w.start()
    (watch / "wf.json").write_bytes(b"")
    with pytest.raises(queue.Empty):
        results.get(timeout=2)
    write_wf(watch / "wf.json.part")
    os.replace(watch / "wf.json.part", watch / "wf.json")
    r = wait_result(results)
    assert r.status == "imported"


def test_failed_file_can_be_retried(tmp_path):
    watch = tmp_path / "dl"
    watch.mkdir()
    blocker = tmp_path / "bloque"
    blocker.write_text("x", encoding="utf-8")
    current = {"dest": blocker / "sous"}  # destination that cannot be created
    results = queue.Queue()
    w = FolderWatcher(watch, lambda: current["dest"], results.put)
    try:
        w.start()
        write_wf(watch / "wf.json")
        assert wait_result(results).status == "error"
        assert w.failed_count == 1
        current["dest"] = tmp_path / "ok"  # the drive is back
        w.retry_failed()
        assert wait_result(results).status == "imported"
        assert (tmp_path / "ok" / "wf.json").exists()
        assert w.failed_count == 0
    finally:
        w.stop()


def test_healthy_false_when_watch_dir_disappears(env):
    w, watch, dest, results = env
    w.start()
    assert w.healthy
    w.stop()  # releases the folder on Windows before deletion
    w.start()
    w._observer.stop()
    w._observer.join()
    assert not w.healthy
