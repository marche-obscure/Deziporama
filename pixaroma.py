"""Episodes of workflows.pixaroma.com: list, folder names and direct import."""

import json
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from i18n import t
from importer import ImportResult, import_file

BASE_URL = "https://workflows.pixaroma.com/"
LIST_FILE = "episodes.js"
TIMEOUT = 20  # seconds, per network request
USER_AGENT = "Deziporama (https://github.com/marche-obscure/Deziporama)"
_EPISODE_FOLDER = re.compile(r"^Ep(\d+) - ")


class PixaromaError(Exception):
    """The episode list could not be read (network or unexpected content)."""


@dataclass
class Episode:
    number: int
    title: str
    category: str
    download_path: str
    size: int
    workflow_count: int
    youtube: str
    coming_soon: bool

    @property
    def folder_name(self) -> str:
        return folder_name(self.number, self.title)

    @property
    def zip_name(self) -> str:
        return Path(self.download_path).name

    def url(self, base_url: str = BASE_URL) -> str:
        return urllib.parse.urljoin(base_url, urllib.parse.quote(self.download_path))


def folder_name(number: int, title: str) -> str:
    """"Ep## - Title", with the characters Windows forbids in folder names replaced."""
    clean = re.sub(r"\s*[|:]\s*", " - ", title)
    clean = re.sub(r'[/\\*]', " ", clean)
    clean = re.sub(r'[?"<>\x00-\x1f]', "", clean)
    clean = re.sub(r"\s+", " ", clean).strip().rstrip(". ")
    return f"Ep{number:02d} - {clean}"


def parse_episodes(text: str) -> list[Episode]:
    """Reads the content of episodes.js ("window.EPISODES = [...];"), newest first."""
    body = re.sub(r"^\s*window\.EPISODES\s*=\s*", "", text.lstrip("﻿")).strip().rstrip(";")
    try:
        data = json.loads(body)
        episodes = [Episode(number=int(item["number"]), title=str(item["title"]),
                            category=str(item.get("category", "")),
                            download_path=str(item["downloadPath"]),
                            size=int(item.get("zipSizeBytes") or 0),
                            workflow_count=int(item.get("workflowCount") or 0),
                            youtube=str(item.get("youtube", "")),
                            coming_soon=bool(item.get("comingSoon", False)))
                    for item in data]
    except (ValueError, TypeError, KeyError) as e:
        raise PixaromaError(f"unexpected episode list ({e.__class__.__name__})") from e
    return sorted(episodes, key=lambda ep: ep.number, reverse=True)


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=TIMEOUT)


def fetch_episodes(base_url: str = BASE_URL) -> list[Episode]:
    try:
        with _open(urllib.parse.urljoin(base_url, LIST_FILE)) as response:
            text = response.read().decode("utf-8-sig")
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as e:
        raise PixaromaError(str(getattr(e, "reason", e))) from e
    return parse_episodes(text)


def _episode_numbers(folder: Path) -> tuple[set[int], list[Path]]:
    """Episode numbers of the "Ep## - ..." folders in `folder`, and its other subfolders."""
    numbers, others = set(), []
    try:
        for p in Path(folder).iterdir():
            if p.is_dir():
                m = _EPISODE_FOLDER.match(p.name)
                if m:
                    numbers.add(int(m.group(1)))
                else:
                    others.append(p)
    except OSError:
        pass
    return numbers, others


def imported_numbers(folder: Path) -> set[int]:
    """Episodes already present as "Ep## - ..." folders, in `folder` or one of its direct
    subfolders (e.g. one subfolder per year)."""
    numbers, subfolders = _episode_numbers(folder)
    for sub in subfolders:
        numbers |= _episode_numbers(sub)[0]
    return numbers


def import_episode(episode: Episode, dest_dir: Path, base_url: str = BASE_URL) -> ImportResult:
    """Downloads the episode zip, then extracts it into dest_dir as "Ep## - Title". Never raises."""
    work = Path(tempfile.mkdtemp(prefix="deziporama-"))
    archive = work / episode.zip_name
    try:
        try:
            with _open(episode.url(base_url)) as response, open(archive, "wb") as out:
                shutil.copyfileobj(response, out)
        except (urllib.error.URLError, OSError) as e:
            return ImportResult("error", archive, None,
                                t("msg_download_failed", error=getattr(e, "reason", e)))
        # The temporary zip is deleted with its folder, not sent to the Recycle Bin.
        return import_file(archive, Path(dest_dir), trash=lambda path: None,
                           folder_name=episode.folder_name)
    finally:
        shutil.rmtree(work, ignore_errors=True)
