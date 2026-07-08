from __future__ import annotations

import logging
import winreg
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "Nova"


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_VALUE)
        return True
    except OSError:
        return False


def set_startup(cmd: str | None) -> None:
    """cmd = command line to run at logon; None removes the entry."""
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if cmd:
            winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, _RUN_VALUE)
            except OSError:
                pass


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
        on_launcher: Callable[[], None] | None = None,
        startup_cmd: str | None = None,
    ) -> None:
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._startup_cmd = startup_cmd
        self._listening = True

        menu_items: list[pystray.MenuItem] = [
            pystray.MenuItem(
                lambda item: "Listening: ON" if self._listening else "Listening: OFF",
                self._toggle,
            ),
        ]
        if on_notes is not None:
            menu_items.append(pystray.MenuItem("Notes", on_notes))
        if on_launcher is not None:
            menu_items.append(pystray.MenuItem("App Launcher", on_launcher))
        if startup_cmd is not None:
            menu_items.append(
                pystray.MenuItem(
                    "Start with Windows",
                    self._toggle_startup,
                    checked=lambda item: startup_enabled(),
                )
            )
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

    def _toggle_startup(self) -> None:
        set_startup(None if startup_enabled() else self._startup_cmd)
        self._icon.update_menu()

    def _quit(self) -> None:
        self._on_quit()
        self._icon.stop()

    def run_detached(self) -> None:
        self._icon.run_detached()
