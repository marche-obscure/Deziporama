"""Détection et import des workflows ComfyUI (.json / .zip)."""

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable

from send2trash import send2trash

MAX_JSON_BYTES = 50 * 1024 * 1024          # au-delà, un .json n'est pas considéré comme un workflow
MAX_EXTRACT_BYTES = 2 * 1024 * 1024 * 1024  # taille maximale d'une archive une fois extraite
# Erreurs de lecture qui signifient « ce n'est pas un workflow exploitable » plutôt qu'un échec.
_UNREADABLE = (ValueError, RecursionError, RuntimeError, NotImplementedError, MemoryError)


@dataclass
class ImportResult:
    status: str  # "imported" | "ignored" | "error"
    source: Path
    target: Path | None = None
    message: str = ""


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
    except _UNREADABLE:
        return False


def is_workflow_json(path: Path) -> bool:
    try:
        if Path(path).stat().st_size > MAX_JSON_BYTES:
            return False
        return _is_workflow_text(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        return False


def is_workflow_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".json"):
                    continue
                if info.file_size > MAX_JSON_BYTES:
                    continue
                try:
                    text = z.read(info).decode("utf-8-sig")
                except (UnicodeDecodeError, *_UNREADABLE):
                    continue
                if _is_workflow_text(text):
                    return True
    except (zipfile.BadZipFile, OSError, *_UNREADABLE):
        return False
    return False


def unique_path(path: Path) -> Path:
    """Renvoie `path`, ou `nom (2)`, `nom (3)`… si le chemin existe déjà."""
    if not path.exists():
        return path
    stem, suffix = (path.stem, path.suffix) if path.suffix else (path.name, "")
    n = 2
    while True:
        candidate = path.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _check_entries(z: zipfile.ZipFile, root: Path) -> None:
    """Refuse toute entrée dont le chemin sortirait du dossier d'extraction."""
    total = sum(info.file_size for info in z.infolist())
    if total > MAX_EXTRACT_BYTES:
        raise ValueError(f"archive trop volumineuse une fois extraite ({total / 1024**3:.1f} Go)")
    root = root.resolve()
    for name in z.namelist():
        win = PureWindowsPath(name)
        if PurePosixPath(name).is_absolute() or win.is_absolute() or win.drive or win.root:
            raise ValueError(f"chemin dangereux dans l'archive : {name}")
        if not (root / name).resolve().is_relative_to(root):
            raise ValueError(f"chemin dangereux dans l'archive : {name}")


def _import_json(source: Path, dest_dir: Path) -> ImportResult:
    if not is_workflow_json(source):
        return ImportResult("ignored", source, None, "pas un workflow ComfyUI")
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Copie sous un nom temporaire puis renommage : jamais de workflow tronqué dans ComfyUI.
    tmp = dest_dir / f".import-{source.name}.tmp"
    try:
        shutil.copyfile(source, tmp)
        target = unique_path(dest_dir / source.name)
        tmp.rename(target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:
        source.unlink()
    except OSError as e:
        return ImportResult("imported", source, target,
                            f"le fichier d'origine n'a pas pu être supprimé : {e}")
    return ImportResult("imported", source, target)


def _import_zip(source: Path, dest_dir: Path, trash: Callable[[str], None]) -> ImportResult:
    if not is_workflow_zip(source):
        return ImportResult("ignored", source, None, "aucun workflow ComfyUI dans l'archive")
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=dest_dir, prefix=".import-"))
    try:
        with zipfile.ZipFile(source) as z:
            _check_entries(z, tmp)
            z.extractall(tmp)
        target = unique_path(dest_dir / source.stem)
        tmp.rename(target)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    try:
        trash(str(source))
    except Exception as e:  # noqa: BLE001 — le workflow est installé : ce n'est pas un échec
        return ImportResult("imported", source, target,
                            f"le zip n'a pas pu être mis à la Corbeille : {e}")
    return ImportResult("imported", source, target)


def import_file(source: Path, dest_dir: Path,
                trash: Callable[[str], None] = send2trash) -> ImportResult:
    """Range un workflow téléchargé dans `dest_dir`. Ne lève jamais d'exception."""
    source, dest_dir = Path(source), Path(dest_dir)
    try:
        ext = source.suffix.lower()
        if ext == ".json":
            return _import_json(source, dest_dir)
        if ext == ".zip":
            return _import_zip(source, dest_dir, trash)
        return ImportResult("ignored", source, None, "extension non prise en charge")
    except Exception as e:  # noqa: BLE001 — l'appelant ne doit jamais planter
        return ImportResult("error", source, None, str(e) or e.__class__.__name__)
