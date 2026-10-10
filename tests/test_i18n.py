import re
import string

import pytest

import i18n


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_three_languages():
    assert i18n.LANGUAGES == {"en": "English", "fr": "Français", "de": "Deutsch"}


@pytest.mark.parametrize("code", ["fr", "de"])
def test_every_key_translated_with_same_placeholders(code):
    english = i18n.TEXTS["en"]
    other = i18n.TEXTS[code]
    assert set(other) == set(english)
    for key, text in english.items():
        assert placeholders(other[key]) == placeholders(text), key
        assert other[key].strip(), key


def test_translations_differ_from_english():
    same = [k for k, v in i18n.TEXTS["fr"].items() if v == i18n.TEXTS["en"][k]]
    assert len(same) <= 3, same  # a few words are identical in both languages


def test_t_uses_current_language():
    assert i18n.t("start") == "Start"
    i18n.set_language("fr")
    assert i18n.t("start") == "Démarrer"
    i18n.set_language("de")
    assert i18n.t("start") == "Starten"


def test_t_formats_values():
    i18n.set_language("fr")
    assert i18n.t("log_watching", path="C:/dl") == "Surveillance de C:/dl."


def test_unknown_language_falls_back_to_english():
    i18n.set_language("xx")
    assert i18n.get_language() == "en"


def test_system_language_is_supported():
    assert i18n.system_language() in i18n.LANGUAGES


def test_language_prompt_in_all_three_languages():
    prompt = i18n.LANGUAGE_PROMPT
    assert "language" in prompt and "langue" in prompt and "Sprache" in prompt


def test_root_labels_cover_all_languages():
    assert i18n.root_labels() == {"(root)", "(racine)", "(Stammordner)"}


def test_import_messages_follow_language(tmp_path):
    import json
    import zipfile

    from importer import import_file

    i18n.set_language("fr")
    other = tmp_path / "x.json"
    other.write_text('{"a": 1}', encoding="utf-8")
    assert import_file(other, tmp_path / "out", trash=lambda p: None).message == "pas un workflow ComfyUI"

    src = tmp_path / "pack.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("wf.json", json.dumps({"nodes": [], "links": []}))

    def broken(path):
        raise OSError("verrou")

    i18n.set_language("de")
    r = import_file(src, tmp_path / "out", trash=broken)
    assert r.message.startswith("das ZIP konnte nicht in den Papierkorb verschoben werden")


def test_shortcut_error_follows_language(tmp_path):
    import shortcut

    i18n.set_language("fr")
    with pytest.raises(OSError, match="dossier du bureau introuvable"):
        shortcut.create(tmp_path / "absent")
