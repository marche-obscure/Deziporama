"""Application icon in the notification area (next to the clock)."""

from typing import Callable

import pystray
from PIL import Image, ImageDraw

import logo
from i18n import t

TITLE = "Deziporama"


def make_image() -> Image.Image:
    """Icon taken from the logo; otherwise a rounded blue square with a download arrow."""
    from_logo = logo.icon_image(64)
    if from_logo is not None:
        return from_logo
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=12, fill=(37, 99, 235))
    d.rectangle((27, 12, 37, 34), fill="white")
    d.polygon([(16, 32), (48, 32), (32, 48)], fill="white")
    d.rectangle((14, 50, 50, 54), fill="white")
    return img


class TrayIcon:
    """Callbacks are called from the pystray thread, never from Tkinter."""

    def __init__(self, on_show: Callable[[], None], on_quit: Callable[[], None]) -> None:
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: t("tray_show"), lambda icon, item: on_show(), default=True),
            pystray.MenuItem(lambda item: t("tray_quit"), lambda icon, item: on_quit()),
        )
        self.icon = pystray.Icon("deziporama", make_image(), TITLE, menu)
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

    def refresh_menu(self) -> None:
        """Menu texts are evaluated on display; Windows needs a refresh after a language change."""
        if self._started:
            self.icon.update_menu()

    def stop(self) -> None:
        if self._started:
            self.icon.stop()
            self._started = False
