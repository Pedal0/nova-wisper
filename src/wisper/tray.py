from __future__ import annotations

import logging
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def _make_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=(80, 140, 255, 255))
    d.ellipse((22, 18, 42, 38), fill=(255, 255, 255, 210))
    return img


class TrayApp:
    """System tray icon: toggles listening, opens notes, quits the app."""

    def __init__(
        self,
        on_toggle: Callable[[bool], None],
        on_quit: Callable[[], None],
        on_notes: Callable[[], None] | None = None,
    ) -> None:
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._listening = True

        menu_items: list[pystray.MenuItem] = [
            pystray.MenuItem(
                lambda item: "Listening: ON" if self._listening else "Listening: OFF",
                self._toggle,
            ),
        ]
        if on_notes is not None:
            menu_items.append(pystray.MenuItem("Notes", on_notes))
        menu_items.append(pystray.MenuItem("Quit", self._quit))

        self._icon = pystray.Icon(
            "nova",
            _make_icon(),
            "Nova voice dictation",
            menu=pystray.Menu(*menu_items),
        )

    def _toggle(self) -> None:
        self._listening = not self._listening
        self._on_toggle(self._listening)
        self._icon.update_menu()

    def _quit(self) -> None:
        self._on_quit()
        self._icon.stop()

    def run_detached(self) -> None:
        self._icon.run_detached()
