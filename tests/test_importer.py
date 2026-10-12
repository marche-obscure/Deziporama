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


# --- Detection ---------------------------------------------------------------

def test_ui_format_detected():
    assert is_workflow_data(UI)


def test_api_format_detected():
    assert is_workflow_data(API)


def test_other_dict_ignored():
    assert not is_workflow_data({"name": "x"})


def test_empty_dict_ignored():
    assert not is_workflow_data({})


@pytest.mark.parametrize("content", ["[1, 2]", "42", "", "not json"])
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
    z.write_bytes(b"not a zip")
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
    assert leftovers(dest) == ["Pack"]


def test_import_zip_duplicate_folder(tmp_path):
    dest = tmp_path / "out"
    (dest / "pack").mkdir(parents=True)
    src = make_zip(tmp_path / "pack.zip", {"wf.json": json.dumps(UI)})
    r = import_file(src, dest, trash=lambda p: None)
    assert r.target.name == "Pack (2)"


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
    src.write_bytes(b"not a zip")
    r = import_file(src, tmp_path / "out", trash=lambda p: None)
    assert r.status == "ignored"
    assert src.exists()


def test_unwritable_destination_is_error(tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    src = write_wf(tmp_path / "wf.json")
    r = import_file(src, blocker / "sous", trash=lambda p: None)
    assert r.status == "error"
    assert src.exists()


def test_trash_failure_still_reported_imported(tmp_path):
    src = make_zip(tmp_path / "pack.zip", {"wf.json": json.dumps(UI)})

    def broken_trash(path):
        raise OSError("file locked")

    r = import_file(src, tmp_path / "out", trash=broken_trash)
    assert r.status == "imported"
    assert r.target == tmp_path / "out" / "pack"
    assert "Recycle Bin" in r.message


# --- Robustness (minor review findings) ---------------------------------------

import importer  # noqa: E402


def test_interrupted_json_copy_leaves_nothing(tmp_path, monkeypatch):
    src = write_wf(tmp_path / "wf.json")
    dest = tmp_path / "out"

    def broken_copy(a, b, *args, **kwargs):
        with open(b, "wb") as fh:
            fh.write(b'{"nodes"')  # copie partielle
        raise OSError("drive unplugged")

    monkeypatch.setattr(importer.shutil, "copyfile", broken_copy)
    r = import_file(src, dest, trash=lambda p: None)
    assert r.status == "error"
    assert src.exists()
    assert leftovers(dest) == []


def test_json_source_undeletable_still_imported(tmp_path, monkeypatch):
    src = write_wf(tmp_path / "wf.json")
    real_unlink = importer.Path.unlink

    def locked_unlink(self, *a, **k):
        if self == src:
            raise PermissionError("locked")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(importer.Path, "unlink", locked_unlink)
    r = import_file(src, tmp_path / "out", trash=lambda p: None)
    assert r.status == "imported"
    assert (tmp_path / "out" / "wf.json").exists()
    assert r.message


def test_very_deep_json_ignored(tmp_path):
    f = tmp_path / "deep.json"
    f.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
    assert not is_workflow_json(f)
    assert import_file(f, tmp_path / "out", trash=lambda p: None).status == "ignored"


def test_encrypted_zip_ignored(tmp_path):
    src = make_zip(tmp_path / "secret.zip", {"wf.json": json.dumps(UI)})
    # zipfile cannot write encrypted zips: set the "encrypted" flag bit
    # in the local header and the central directory; reading then requires a password.
    raw = bytearray(src.read_bytes())
    raw[raw.find(b"PK\x03\x04") + 6] |= 0x1
    raw[raw.find(b"PK\x01\x02") + 8] |= 0x1
    src.write_bytes(bytes(raw))
    assert not is_workflow_zip(src)
    assert import_file(src, tmp_path / "out", trash=lambda p: None).status == "ignored"


def test_oversized_json_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MAX_JSON_BYTES", 10)
    f = write_wf(tmp_path / "wf.json")
    assert not is_workflow_json(f)


def test_oversized_json_entry_in_zip_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MAX_JSON_BYTES", 10)
    z = make_zip(tmp_path / "p.zip", {"wf.json": json.dumps(UI)})
    assert not is_workflow_zip(z)


def test_zip_too_big_when_extracted_is_error(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MAX_EXTRACT_BYTES", 100)
    src = make_zip(tmp_path / "pack.zip", {"wf.json": json.dumps(UI), "big.bin": b"0" * 1000})
    dest = tmp_path / "out"
    trashed = []
    r = import_file(src, dest, trash=trashed.append)
    assert r.status == "error"
    assert "too large" in r.message
    assert trashed == [] and src.exists()
    assert leftovers(dest) == []


# --- Zip holding a single folder at its root ----------------------------------

def test_single_root_folder_is_flattened(tmp_path):
    src = make_zip(tmp_path / "Ep33 Workflows.zip", {
        "EP33 Workflows/wf.json": json.dumps(UI),
        "EP33 Workflows/images/a.png": b"png",
    })
    dest = tmp_path / "out"
    r = import_file(src, dest, trash=lambda p: None)
    assert r.status == "imported"
    assert r.target == dest / "EP33 Workflows"
    assert (dest / "EP33 Workflows" / "wf.json").exists()
    assert (dest / "EP33 Workflows" / "images" / "a.png").exists()
    assert leftovers(dest) == ["Ep33 Workflows"]


def test_single_folder_plus_root_file_not_flattened(tmp_path):
    src = make_zip(tmp_path / "pack.zip", {"Folder/wf.json": json.dumps(UI), "readme.txt": "x"})
    dest = tmp_path / "out"
    r = import_file(src, dest, trash=lambda p: None)
    assert r.target == dest / "pack"
    assert (dest / "pack" / "Folder" / "wf.json").exists()
    assert (dest / "pack" / "readme.txt").exists()


def test_two_root_folders_not_flattened(tmp_path):
    src = make_zip(tmp_path / "pack.zip", {"A/wf.json": json.dumps(UI), "B/autre.json": json.dumps(UI)})
    dest = tmp_path / "out"
    r = import_file(src, dest, trash=lambda p: None)
    assert r.target == dest / "pack"
    assert (dest / "pack" / "A" / "wf.json").exists()
    assert (dest / "pack" / "B" / "autre.json").exists()


def test_macosx_folder_ignored_and_not_extracted(tmp_path):
    src = make_zip(tmp_path / "pack.zip", {
        "EP33/wf.json": json.dumps(UI),
        "__MACOSX/EP33/._wf.json": b"mac",
        "__MACOSX/._EP33": b"mac",
    })
    dest = tmp_path / "out"
    r = import_file(src, dest, trash=lambda p: None)
    assert r.target == dest / "EP33"
    assert (dest / "EP33" / "wf.json").exists()
    assert not list(dest.rglob("__MACOSX"))
    assert leftovers(dest) == ["Ep33"]


def test_flattened_folder_name_collision(tmp_path):
    dest = tmp_path / "out"
    (dest / "EP33 Workflows").mkdir(parents=True)
    src = make_zip(tmp_path / "Ep33 Workflows.zip", {"EP33 Workflows/wf.json": json.dumps(UI)})
    r = import_file(src, dest, trash=lambda p: None)
    assert r.target.name == "Ep33 Workflows (2)"
    assert (dest / "EP33 Workflows (2)" / "wf.json").exists()


def test_single_root_folder_with_name_sanitized_by_windows(tmp_path):
    # Windows forbids a trailing space: extraction creates "EP33", not "EP33 ".
    src = make_zip(tmp_path / "pack.zip", {"EP33 /wf.json": json.dumps(UI)})
    dest = tmp_path / "out"
    r = import_file(src, dest, trash=lambda p: None)
    assert r.status == "imported", r.message
    assert r.target == dest / "EP33"
    assert (dest / "EP33" / "wf.json").exists()


# --- Case of the folder created by extraction ----------------------------------

from importer import capitalize_words  # noqa: E402


@pytest.mark.parametrize("raw, expected", [
    ("EP33 Workflows", "Ep33 Workflows"),
    ("FLUX dev PACK", "Flux Dev Pack"),
    ("my_flux-pack", "My_Flux-Pack"),
    ("o'neil pack", "O'neil Pack"),
    ("33 WORKFLOWS", "33 Workflows"),
    ("ÅSA  ØRE", "Åsa  Øre"),
])
def test_capitalize_words(raw, expected):
    assert capitalize_words(raw) == expected


def test_flattened_folder_name_capitalized_content_untouched(tmp_path):
    src = make_zip(tmp_path / "Ep33 Workflows.zip", {
        "EP33 Workflows/WF_Main.json": json.dumps(UI),
        "EP33 Workflows/IMAGES/Ref A.PNG": b"png",
    })
    dest = tmp_path / "out"
    r = import_file(src, dest, trash=lambda p: None)
    assert r.target.name == "Ep33 Workflows"
    assert leftovers(dest) == ["Ep33 Workflows"]
    assert sorted(p.name for p in (dest / "Ep33 Workflows").iterdir()) == ["IMAGES", "WF_Main.json"]
    assert [p.name for p in (dest / "Ep33 Workflows" / "IMAGES").iterdir()] == ["Ref A.PNG"]


def test_zip_named_folder_capitalized(tmp_path):
    src = make_zip(tmp_path / "FLUX dev PACK.zip", {"wf.json": json.dumps(UI)})
    dest = tmp_path / "out"
    r = import_file(src, dest, trash=lambda p: None)
    assert r.target.name == "Flux Dev Pack"
    assert leftovers(dest) == ["Flux Dev Pack"]


def test_capitalized_name_collision_ignores_case(tmp_path):
    dest = tmp_path / "out"
    (dest / "EP33 WORKFLOWS").mkdir(parents=True)
    src = make_zip(tmp_path / "x.zip", {"EP33 Workflows/wf.json": json.dumps(UI)})
    r = import_file(src, dest, trash=lambda p: None)
    assert r.target.name == "Ep33 Workflows (2)"
    assert sorted(leftovers(dest)) == ["EP33 WORKFLOWS", "Ep33 Workflows (2)"]


# --- Progress -------------------------------------------------------------------------

def test_zip_extraction_reports_progress(tmp_path):
    src = make_zip(tmp_path / "pack.zip", {"wf.json": json.dumps(UI), "a.bin": b"x" * 5000, "b.bin": b"y" * 3000})
    seen = []
    r = import_file(src, tmp_path / "out", trash=lambda p: None, progress=lambda done, total: seen.append((done, total)))
    assert r.status == "imported"
    total = seen[-1][1]
    assert total == len(json.dumps(UI)) + 8000
    assert seen[-1][0] == total  # ends at 100 %
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)  # never goes back
