"""Deziporama logo: icon ("DEZ" + slider crop) and window banner."""

from functools import lru_cache
from pathlib import Path

from PIL import Image

LOGO_PATH = Path(__file__).with_name("assets") / "deziporama.webp"
ICO_PATH = LOGO_PATH.with_name("deziporama.ico")  # generated from the logo, not versioned
# Areas of the original logo (2000 x 2000 px).
ICON_BOX = (60, 660, 760, 1360)       # "DEZ" with the green slider: readable at 16-32 px
BANNER_BOX = (40, 560, 1960, 1320)    # the whole word and the zipper
BANNER_BACKGROUND = "#1c1b20"         # dark logo background, to extend the banner


@lru_cache(maxsize=4)
def _load(path: Path) -> Image.Image | None:
    try:
        with Image.open(path) as im:
            return im.convert("RGBA")
    except OSError:
        return None


def icon_image(size: int = 64) -> Image.Image | None:
    logo = _load(LOGO_PATH)
    if logo is None:
        return None
    return logo.crop(ICON_BOX).resize((size, size), Image.LANCZOS)


def banner_image(width: int = 420) -> Image.Image | None:
    logo = _load(LOGO_PATH)
    if logo is None:
        return None
    band = logo.crop(BANNER_BOX)
    height = round(width * band.height / band.width)
    return band.resize((width, height), Image.LANCZOS)


def write_ico(path: Path) -> bool:
    """Writes the icon as .ico (desktop shortcut). False if the logo is missing."""
    img = icon_image(256)
    if img is None:
        return False
    img.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    return True
