"""Guard: the application source (strings and comments) must be in English."""

import io
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted([*ROOT.glob("*.py"), *ROOT.glob("tests/*.py"), *ROOT.glob("*.bat")])
FRENCH_CHARS = re.compile(r"[àâçéèêëîïôûùüÿœÀÂÇÉÈÊËÎÏÔÛÙÜŸŒ«»]")
FRENCH_WORDS = re.compile(
    r"\b(le|la|les|des|une|est|dans|pour|avec|sans|fichier|dossier|erreur|fenêtre|raccourci|"
    r"surveillance|démarrer|quitter|annuler|afficher|bureau|réduire|lancer|horloge|pas|aucun|chaque|depuis|"
    r"corbeille|workflows? (?:non|déjà))\b",
    re.IGNORECASE)
# The guard itself has to spell out French words to detect them.
ALLOWED = {"test_english.py", "i18n.py", "test_i18n.py", "test_app.py", "test_tray.py"}  # translations live in i18n.py


def texts(path: Path):
    """Comments and string literals of a Python file, or every line of a batch file."""
    source = path.read_text(encoding="utf-8")
    if path.suffix == ".bat":
        yield from enumerate(source.splitlines(), 1)
        return
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING, tokenize.FSTRING_MIDDLE):
            yield tok.start[0], tok.string


@pytest.mark.parametrize("path", [p for p in SOURCES if p.name not in ALLOWED], ids=lambda p: p.name)
def test_no_french(path):
    found = [f"{path.name}:{line}: {text.strip()[:80]}"
             for line, text in texts(path)
             if FRENCH_CHARS.search(text) or FRENCH_WORDS.search(text)]
    assert not found, "\n".join(found)
