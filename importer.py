"""Détection et import des workflows ComfyUI (.json / .zip)."""

import json
import zipfile
from pathlib import Path


def is_workflow_data(data: object) -> bool:
    """Vrai si `data` est un workflow ComfyUI, au format interface ou API."""
    if not isinstance(data, dict) or not data:
        return False
    if isinstance(data.get("nodes"), list) and "links" in data:
        return True
    return all(isinstance(v, dict) and "class_type" in v for v in data.values())


def _is_workflow_text(text: str) -> bool:
    try:
        return is_workflow_data(json.loads(text))
    except ValueError:
        return False


def is_workflow_json(path: Path) -> bool:
    try:
        return _is_workflow_text(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        return False


def is_workflow_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".json"):
                    continue
                try:
                    text = z.read(info).decode("utf-8-sig")
                except UnicodeDecodeError:
                    continue
                if _is_workflow_text(text):
                    return True
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
    return False
