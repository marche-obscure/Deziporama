"""Icône de l'applicatif dans la zone de notification (près de l'horloge)."""

from typing import Callable

import pystray
from PIL import Image, ImageDraw

TITLE = "Deziporama"


def make_image() -> Image.Image:
    """Icône dessinée à la volée : carré arrondi bleu avec une flèche de téléchargement."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=12, fill=(37, 99, 235))
    d.rectangle((27, 12, 37, 34), fill="white")
    d.polygon([(16, 32), (48, 32), (32, 48)], fill="white")
    d.rectangle((14, 50, 50, 54), fill="white")
    return img


class TrayIcon:
    """Les callbacks sont appelés depuis le thread de pystray, jamais depuis Tkinter."""

    def __init__(self, on_show: Callable[[], None], on_quit: Callable[[], None]) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Afficher", lambda icon, item: on_show(), default=True),
            pystray.MenuItem("Quitter", lambda icon, item: on_quit()),
        )
        self.icon = pystray.Icon("importeur-workflows", make_image(), TITLE, menu)
        self._started = False

    def show(self) -> None:
        if not self._started:
            self.icon.run_detached()
            self._started = True
        self.icon.visible = True

    def hide(self) -> None:
        if self._started:
            self.icon.visible = False

    def set_tooltip(self, text: str) -> None:
        self.icon.title = text

    def stop(self) -> None:
        if self._started:
            self.icon.stop()
            self._started = False
