import json
import zipfile

import pytest

from importer import is_workflow_data, is_workflow_json, is_workflow_zip

UI = {"nodes": [], "links": [], "version": 0.4}
API = {"3": {"class_type": "KSampler", "inputs": {}}, "4": {"class_type": "SaveImage", "inputs": {}}}


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


# --- Détection ---------------------------------------------------------------

def test_ui_format_detected():
    assert is_workflow_data(UI)


def test_api_format_detected():
    assert is_workflow_data(API)


def test_other_dict_ignored():
    assert not is_workflow_data({"name": "x"})


def test_empty_dict_ignored():
    assert not is_workflow_data({})


@pytest.mark.parametrize("content", ["[1, 2]", "42", "", "pas du json"])
def test_non_object_json_ignored(tmp_path, content):
    f = tmp_path / "x.json"
    f.write_text(content, encoding="utf-8")
    assert not is_workflow_json(f)


def test_json_with_bom(tmp_path):
    f = tmp_path / "wf.json"
    f.write_text(json.dumps(UI), encoding="utf-8-sig")
    assert is_workflow_json(f)


def test_zip_with_workflow(tmp_path):
    z = make_zip(tmp_path / "p.zip", {"sub/wf.json": json.dumps(UI), "img.png": b"\x89PNG"})
    assert is_workflow_zip(z)


def test_zip_without_workflow(tmp_path):
    z = make_zip(tmp_path / "p.zip", {"readme.txt": "hello", "data.json": json.dumps({"a": 1})})
    assert not is_workflow_zip(z)


def test_corrupt_zip(tmp_path):
    z = tmp_path / "p.zip"
    z.write_bytes(b"pas un zip")
    assert not is_workflow_zip(z)


# --- Import ------------------------------------------------------------------

from importer import ImportResult, import_file, unique_path  # noqa: E402


def write_wf(path, data=UI):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def leftovers(dest):
    return sorted(p.name for p in dest.iterdir()) if dest.exists() else []


def test_unique_path_free(tmp_path):
    assert unique_path(tmp_path / "a.json") == tmp_path / "a.json"


def test_unique_path_suffixes(tmp_path):
    (tmp_path / "a.json").touch()
    (tmp_path / "a (2).json").touch()
    assert unique_path(tmp_path / "a.json") == tmp_path / "a (3).json"
    (tmp_path / "pack").mkdir()
    assert unique_path(tmp_path / "pack") == tmp_path / "pack (2)"


def test_import_json_moves(tmp_path):
    src = write_wf(tmp_path / "wf.json")
    content = src.read_text(encoding="utf-8")
    dest = tmp_path / "out" / "salon"
    r = import_file(src, dest, trash=lambda p: None)
    assert isinstance(r, ImportResult)
    assert r.status == "imported"
    assert r.target == dest / "wf.json"
    assert not src.exists()
    assert r.target.read_text(encoding="utf-8") == content


def test_import_json_duplicate(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "wf.json").write_text("ancien", encoding="utf-8")
    r = import_file(write_wf(tmp_path / "wf.json"), dest, trash=lambda p: None)
    assert r.target == dest / "wf (2).json"
    assert (dest / "wf.json").read_text(encoding="utf-8") == "ancien"


def test_import_non_workflow_ignored(tmp_path):
    src = write_wf(tmp_path / "x.json", {"a": 1})
    r = import_file(src, tmp_path / "out", trash=lambda p: None)
    assert r.status == "ignored"
    assert src.exists()


def test_import_zip_extracts_all(tmp_path):
    src = make_zip(tmp_path / "pack.zip", {"wf.json": json.dumps(UI), "images/a.png": b"png"})
    dest = tmp_path / "out"
    trashed = []
    r = import_file(src, dest, trash=trashed.append)
    assert r.status == "imported"
    assert r.target == dest / "pack"
    assert (dest / "pack" / "wf.json").exists()
    assert (dest / "pack" / "images" / "a.png").read_bytes() == b"png"
    assert trashed == [str(src)]
    assert leftovers(dest) == ["pack"]


def test_import_zip_duplicate_folder(tmp_path):
    dest = tmp_path / "out"
    (dest / "pack").mkdir(parents=True)
    src = make_zip(tmp_path / "pack.zip", {"wf.json": json.dumps(UI)})
    r = import_file(src, dest, trash=lambda p: None)
    assert r.target == dest / "pack (2)"


@pytest.mark.parametrize("evil", ["../evil.txt", "C:/evil.txt", "/evil.txt"])
def test_zip_slip_rejected(tmp_path, evil):
    src = make_zip(tmp_path / "pack.zip", {"wf.json": json.dumps(UI), evil: "x"})
    dest = tmp_path / "out" / "salon"
    trashed = []
    r = import_file(src, dest, trash=trashed.append)
    assert r.status == "error"
    assert trashed == []
    assert src.exists()
    assert not (tmp_path / "out" / "evil.txt").exists()
    assert not (tmp_path / "evil.txt").exists()
    assert leftovers(dest) == []


def test_corrupt_zip_ignored(tmp_path):
    src = tmp_path / "pack.zip"
    src.write_bytes(b"pas un zip")
    r = import_file(src, tmp_path / "out", trash=lambda p: None)
    assert r.status == "ignored"
    assert src.exists()


def test_unwritable_destination_is_error(tmp_path):
    blocker = tmp_path / "fichier"
    blocker.write_text("x", encoding="utf-8")
    src = write_wf(tmp_path / "wf.json")
    r = import_file(src, blocker / "sous", trash=lambda p: None)
    assert r.status == "error"
    assert src.exists()


def test_trash_failure_still_reported_imported(tmp_path):
    src = make_zip(tmp_path / "pack.zip", {"wf.json": json.dumps(UI)})

    def broken_trash(path):
        raise OSError("fichier verrouillé")

    r = import_file(src, tmp_path / "out", trash=broken_trash)
    assert r.status == "imported"
    assert r.target == tmp_path / "out" / "pack"
    assert "Corbeille" in r.message
