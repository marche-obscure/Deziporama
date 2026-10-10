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
