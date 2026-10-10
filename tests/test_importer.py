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
