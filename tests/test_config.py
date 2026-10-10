import json

from app import DEFAULTS, load_config, save_config


def test_missing_config_gives_defaults(tmp_path):
    assert load_config(tmp_path / "c.json") == DEFAULTS


def test_corrupt_config_gives_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{oops", encoding="utf-8")
    assert load_config(p) == DEFAULTS


def test_roundtrip(tmp_path):
    p = tmp_path / "c.json"
    cfg = dict(DEFAULTS, subfolder="Salon", process_existing=True)
    save_config(cfg, p)
    assert load_config(p) == cfg


def test_missing_key_completed(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"subfolder": "X"}), encoding="utf-8")
    assert load_config(p) == dict(DEFAULTS, subfolder="X")


def test_wrong_types_replaced_by_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"subfolder": 5, "process_existing": "oui", "watch_dir": None}), encoding="utf-8")
    assert load_config(p) == DEFAULTS


def test_save_is_atomic(tmp_path, monkeypatch):
    import app
    p = tmp_path / "c.json"
    save_config(dict(DEFAULTS, subfolder="Ancien"), p)

    def crash(*a, **k):
        raise OSError("crash while writing")

    monkeypatch.setattr(app.os, "replace", crash)
    try:
        save_config(dict(DEFAULTS, subfolder="Nouveau"), p)
    except OSError:
        pass
    assert load_config(p)["subfolder"] == "Ancien"
    assert [f.name for f in tmp_path.iterdir()] == ["c.json"]


def test_valid_subfolder_name():
    from app import valid_subfolder_name
    for ok in ["Salon", "Mes workflows", "Smørrebrød-2026"]:
        assert valid_subfolder_name(ok), ok
    for bad in ["", "  ", ".", "..", r"..\x", "a/b", r"a\b", r"C:\x", "C:", "a:b", "x?", "<x>", "a|b", '"x"', "x*", ".cache"]:
        assert not valid_subfolder_name(bad), bad
