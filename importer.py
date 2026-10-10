"""Detection and import of ComfyUI workflows (.json / .zip)."""

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable

from send2trash import send2trash

MAX_JSON_BYTES = 50 * 1024 * 1024          # above this, a .json is not considered a workflow
MAX_EXTRACT_BYTES = 2 * 1024 * 1024 * 1024  # maximum size of an archive once extracted
# Read errors meaning "not a usable workflow" rather than a failure.
_UNREADABLE = (ValueError, RecursionError, RuntimeError, NotImplementedError, MemoryError)


@dataclass
class ImportResult:
    status: str  # "imported" | "ignored" | "error"
    source: Path
    target: Path | None = None
    message: str = ""


def is_workflow_data(data: object) -> bool:
    """True if `data` is a ComfyUI workflow, in UI or API format."""
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
    """Returns `path`, or `name (2)`, `name (3)`... if the path already exists."""
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
    """Rejects any entry whose path would escape the extraction folder."""
    total = sum(info.file_size for info in z.infolist())
    if total > MAX_EXTRACT_BYTES:
        raise ValueError(f"archive too large once extracted ({total / 1024**3:.1f} GB)")
    root = root.resolve()
    for name in z.namelist():
        win = PureWindowsPath(name)
        if PurePosixPath(name).is_absolute() or win.is_absolute() or win.drive or win.root:
            raise ValueError(f"dangerous path in archive: {name}")
        if not (root / name).resolve().is_relative_to(root):
            raise ValueError(f"dangerous path in archive: {name}")


def _import_json(source: Path, dest_dir: Path) -> ImportResult:
    if not is_workflow_json(source):
        return ImportResult("ignored", source, None, "not a ComfyUI workflow")
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Copy under a temporary name, then rename: never a truncated workflow in ComfyUI.
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
                            f"the original file could not be deleted: {e}")
    return ImportResult("imported", source, target)


def capitalize_words(name: str) -> str:
    """Capital first letter of each word, the rest lowercase (words split by space, _ or -)."""
    return "".join(part[:1].upper() + part[1:].lower()
                   for part in re.split(r"([ _-]+)", name))


def _is_macos_metadata(name: str) -> bool:
    """Technical folder added by the macOS Finder, useless for ComfyUI."""
    return name.split("/", 1)[0] == "__MACOSX"


def _single_root_folder(extracted: Path) -> Path | None:
    """The extracted folder if it is alone at the root (no file next to it), otherwise None.

    Looks at the disk rather than the zip names: Windows fixes some names
    during extraction (trailing space or dot removed).
    """
    children = list(extracted.iterdir())
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return None


def _import_zip(source: Path, dest_dir: Path, trash: Callable[[str], None]) -> ImportResult:
    if not is_workflow_zip(source):
        return ImportResult("ignored", source, None, "no ComfyUI workflow in the archive")
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=dest_dir, prefix=".import-"))
    try:
        with zipfile.ZipFile(source) as z:
            _check_entries(z, tmp)
            members = [n for n in z.namelist() if not _is_macos_metadata(n)]
            z.extractall(tmp, members)
        folder = _single_root_folder(tmp)
        if folder:
            # The zip only holds one folder: place it directly, without a nested folder.
            target = unique_path(dest_dir / capitalize_words(folder.name))
            folder.rename(target)
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            target = unique_path(dest_dir / capitalize_words(source.stem))
            tmp.rename(target)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    try:
        trash(str(source))
    except Exception as e:  # noqa: BLE001 - the workflow is installed: not a failure
        return ImportResult("imported", source, target,
                            f"the zip could not be moved to the Recycle Bin: {e}")
    return ImportResult("imported", source, target)


def import_file(source: Path, dest_dir: Path,
                trash: Callable[[str], None] = send2trash) -> ImportResult:
    """Files a downloaded workflow into `dest_dir`. Never raises."""
    source, dest_dir = Path(source), Path(dest_dir)
    try:
        ext = source.suffix.lower()
        if ext == ".json":
            return _import_json(source, dest_dir)
        if ext == ".zip":
            return _import_zip(source, dest_dir, trash)
        return ImportResult("ignored", source, None, "unsupported extension")
    except Exception as e:  # noqa: BLE001 - the caller must never crash
        return ImportResult("error", source, None, str(e) or e.__class__.__name__)
