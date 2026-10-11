import functools
import http.server
import json
import threading
import zipfile

import pytest

import pixaroma

UI = {"nodes": [], "links": []}


def episode_data(number, title="Some Title", path=None, coming_soon=False, category="Image"):
    return {
        "number": number, "id": f"ep{number}", "title": title, "category": category,
        "youtube": f"https://www.youtube.com/watch?v={number}", "comingSoon": coming_soon,
        "zip": f"Ep{number} Workflows.zip",
        "downloadPath": path or f"workflows/Ep{number} Workflows.zip",
        "zipSizeBytes": 1234, "workflowCount": 2, "workflows": [],
    }


def episodes_js(*episodes):
    return "window.EPISODES = " + json.dumps(list(episodes), indent=4) + ";\n"


@pytest.fixture
def site(tmp_path):
    """A local fake of workflows.pixaroma.com: never touches the real site."""
    root = tmp_path / "site"
    (root / "workflows").mkdir(parents=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    site = type("Site", (), {})()
    site.root = root
    site.base_url = f"http://127.0.0.1:{server.server_address[1]}/"
    yield site
    server.shutdown()


def add_zip(site, name, entries):
    with zipfile.ZipFile(site.root / "workflows" / name, "w") as z:
        for entry, data in entries.items():
            z.writestr(entry, data)


# --- Folder names -----------------------------------------------------------------

@pytest.mark.parametrize("number, title, expected", [
    (1, "ComfyUI Course - Learn ComfyUI From Scratch | Full 5 Hour Course",
     "Ep01 - ComfyUI Course - Learn ComfyUI From Scratch - Full 5 Hour Course"),
    (37, "Free AI Model for Design & Text in ComfyUI | Ming Image 0.1",
     "Ep37 - Free AI Model for Design & Text in ComfyUI - Ming Image 0.1"),
    (33, "Image to 3D Made Easy: Trellis 2 + Pixal3D in ComfyUI",
     "Ep33 - Image to 3D Made Easy - Trellis 2 + Pixal3D in ComfyUI"),
    (5, 'What? A "quoted" <title>/with*bad\\chars.', "Ep05 - What A quoted title with bad chars"),
    (120, "Long run", "Ep120 - Long run"),
])
def test_folder_name(number, title, expected):
    assert pixaroma.folder_name(number, title) == expected


# --- Episode list -----------------------------------------------------------------

def test_parse_episodes_sorted_newest_first():
    eps = pixaroma.parse_episodes(episodes_js(episode_data(1, "First"), episode_data(3, "Third", coming_soon=True)))
    assert [e.number for e in eps] == [3, 1]
    third = eps[0]
    assert third.title == "Third"
    assert third.coming_soon is True
    assert third.category == "Image"
    assert third.workflow_count == 2
    assert third.size == 1234
    assert third.folder_name == "Ep03 - Third"
    assert third.youtube == "https://www.youtube.com/watch?v=3"


def test_parse_episodes_with_bom_and_no_semicolon():
    text = "﻿" + episodes_js(episode_data(2)).rstrip().rstrip(";")
    assert [e.number for e in pixaroma.parse_episodes(text)] == [2]


@pytest.mark.parametrize("text", ["", "window.EPISODES = {", "<html>404</html>", "window.EPISODES = [{\"a\": 1}];"])
def test_parse_episodes_rejects_unexpected_content(text):
    with pytest.raises(pixaroma.PixaromaError):
        pixaroma.parse_episodes(text)


def test_episode_url_is_quoted():
    ep = pixaroma.parse_episodes(episodes_js(episode_data(1, path="workflows/EP01 Workflows.zip")))[0]
    assert ep.url("https://workflows.pixaroma.com/") == "https://workflows.pixaroma.com/workflows/EP01%20Workflows.zip"


def test_fetch_episodes_from_site(site):
    (site.root / "episodes.js").write_text(episodes_js(episode_data(4), episode_data(5)), encoding="utf-8")
    assert [e.number for e in pixaroma.fetch_episodes(site.base_url)] == [5, 4]


def test_fetch_episodes_site_unreachable():
    with pytest.raises(pixaroma.PixaromaError):
        pixaroma.fetch_episodes("http://127.0.0.1:9/")


# --- Imported / new -----------------------------------------------------------------

def test_imported_numbers(tmp_path):
    for name in ["Ep01 - First", "Ep12 - Twelve (2)", "Ep120 - Long", "Other", "Ep7 notes"]:
        (tmp_path / name).mkdir()
    (tmp_path / "Ep03 - A file.json").write_text("{}", encoding="utf-8")
    assert pixaroma.imported_numbers(tmp_path) == {1, 12, 120}


def test_imported_numbers_includes_direct_subfolders(tmp_path):
    (tmp_path / "2025" / "Ep04 - Four").mkdir(parents=True)
    (tmp_path / "2026" / "Ep30 - Thirty").mkdir(parents=True)
    (tmp_path / "2026" / "deep" / "Ep31 - Too deep").mkdir(parents=True)
    (tmp_path / "Ep02 - Two").mkdir()
    assert pixaroma.imported_numbers(tmp_path) == {2, 4, 30}


def test_imported_numbers_missing_folder(tmp_path):
    assert pixaroma.imported_numbers(tmp_path / "absent") == set()


# --- Import -------------------------------------------------------------------------

def test_import_episode_downloads_extracts_and_renames(site, tmp_path):
    add_zip(site, "Ep27 Workflows.zip", {
        "Ep27 Workflows/": "",
        "Ep27 Workflows/Outpaint.json": json.dumps(UI),
    })
    ep = pixaroma.parse_episodes(episodes_js(episode_data(27, "How to Outpaint in ComfyUI + New Control Panel")))[0]
    dest = tmp_path / "Pixaroma"
    r = pixaroma.import_episode(ep, dest, site.base_url)
    assert r.status == "imported", r.message
    assert r.target.name == "Ep27 - How to Outpaint in ComfyUI + New Control Panel"
    assert (r.target / "Outpaint.json").exists()
    assert sorted(p.name for p in dest.iterdir()) == ["Ep27 - How to Outpaint in ComfyUI + New Control Panel"]


def test_import_episode_zip_without_root_folder(site, tmp_path):
    add_zip(site, "Ep2 Workflows.zip", {"a.json": json.dumps(UI), "b.json": json.dumps(UI)})
    ep = pixaroma.parse_episodes(episodes_js(episode_data(2, "Two", path="workflows/Ep2 Workflows.zip")))[0]
    r = pixaroma.import_episode(ep, tmp_path / "Pixaroma", site.base_url)
    assert r.target.name == "Ep02 - Two"
    assert (r.target / "a.json").exists()


def test_import_episode_twice_gets_suffix(site, tmp_path):
    add_zip(site, "Ep9 Workflows.zip", {"Ep9/wf.json": json.dumps(UI)})
    ep = pixaroma.parse_episodes(episodes_js(episode_data(9, "Nine", path="workflows/Ep9 Workflows.zip")))[0]
    pixaroma.import_episode(ep, tmp_path / "P", site.base_url)
    r = pixaroma.import_episode(ep, tmp_path / "P", site.base_url)
    assert r.target.name == "Ep09 - Nine (2)"


def test_import_episode_missing_zip_is_error(site, tmp_path):
    ep = pixaroma.parse_episodes(episodes_js(episode_data(8)))[0]
    r = pixaroma.import_episode(ep, tmp_path / "P", site.base_url)
    assert r.status == "error"
    assert r.source.name == "Ep8 Workflows.zip"
    assert not (tmp_path / "P").exists() or not any((tmp_path / "P").iterdir())


def test_import_episode_leaves_no_temporary_file(site, tmp_path, monkeypatch):
    add_zip(site, "Ep6 Workflows.zip", {"Ep6/wf.json": json.dumps(UI)})
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(pixaroma.tempfile, "tempdir", str(temp_root))
    ep = pixaroma.parse_episodes(episodes_js(episode_data(6)))[0]
    pixaroma.import_episode(ep, tmp_path / "P", site.base_url)
    assert list(temp_root.iterdir()) == []
