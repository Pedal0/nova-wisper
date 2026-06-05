from __future__ import annotations

import logging
from collections.abc import Callable

import keyboard

logger = logging.getLogger(__name__)

# EN/FR Windows key name aliases
_ALIASES: dict[str, frozenset[str]] = {
    "right ctrl":  frozenset({"right ctrl", "ctrl droite"}),
    "ctrl droite": frozenset({"right ctrl", "ctrl droite"}),
    "right alt":   frozenset({"right alt",  "alt droite"}),
    "left alt":    frozenset({"left alt",   "alt gauche"}),
    "right shift": frozenset({"right shift","maj droite"}),
}


class HotkeyListener:
    """Hold-to-talk: on_press on first keydown, on_release on keyup."""

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self._hotkey = hotkey
        self._names = _ALIASES.get(hotkey.lower(), frozenset({hotkey.lower()}))
        self._on_press = on_press
        self._on_release = on_release
        self._held = False
        self._hook = None

    def _handle(self, event: keyboard.KeyboardEvent) -> None:
        if (event.name or "").lower() not in self._names:
            return
        if event.event_type == keyboard.KEY_DOWN:
            if not self._held:  # ignore key auto-repeat
                self._held = True
                try:
                    self._on_press()
                except Exception:
                    logger.exception("on_press raised an exception")
        elif event.event_type == keyboard.KEY_UP:
            if self._held:
                self._held = False
                try:
                    self._on_release()
                except Exception:
                    logger.exception("on_release raised an exception")

    def start(self) -> None:
        self._hook = keyboard.hook(self._handle)
        logger.info("HotkeyListener active on '%s'", self._hotkey)

    def stop(self) -> None:
        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None
