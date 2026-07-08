from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import keyboard

logger = logging.getLogger(__name__)

# EN/FR Windows key name aliases — events carry localized names ("ctrl droite"
# on a French layout), and the raw scan code (29) is identical for BOTH ctrl
# keys, so name matching is the only reliable way to isolate the right one.
_ALIASES: dict[str, frozenset[str]] = {
    "right ctrl":  frozenset({"right ctrl", "ctrl droite"}),
    "ctrl droite": frozenset({"right ctrl", "ctrl droite"}),
    "right alt":   frozenset({"right alt",  "alt droite"}),
    "left alt":    frozenset({"left alt",   "alt gauche"}),
    "right shift": frozenset({"right shift","maj droite"}),
}


class HotkeyListener:
    """Hold-to-talk: on_press on first keydown, on_release on keyup.

    Uses a global blocking hook and swallows the PTT key (returns False), so
    the OS never sees it.  This is required for realtime typing: text is
    injected while the PTT key is still physically held, and a visible
    modifier (right ctrl) would turn every injected letter into a
    Ctrl+<letter> shortcut in the foreground app.
    """

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
        self._unhook: Callable[[], None] | None = None
        self._suppressed = False

    def _dispatch(self, fn: Callable[[], None]) -> None:
        # The blocking callback runs in the low-level hook thread and must
        # return fast (Windows drops slow hooks) — heavy work goes to a thread.
        def run() -> None:
            try:
                fn()
            except Exception:
                logger.exception("hotkey callback raised an exception")
        threading.Thread(target=run, daemon=True).start()

    def _handle_blocking(self, event: keyboard.KeyboardEvent) -> bool:
        """Return True to let the key through, False to swallow it."""
        if (event.name or "").lower() not in self._names:
            return True
        if event.event_type == keyboard.KEY_DOWN:
            if not self._held:  # ignore key auto-repeat
                self._held = True
                self._dispatch(self._on_press)
        elif self._held:
            self._held = False
            self._dispatch(self._on_release)
        return False  # the OS never sees the PTT key

    def start(self) -> None:
        self._unhook = keyboard.hook(self._handle_blocking, suppress=True)
        self._suppressed = True
        logger.info(
            "HotkeyListener active on '%s' (key suppressed from OS)", self._hotkey
        )

    def stop(self) -> None:
        if self._unhook is not None:
            keyboard.unhook(self._unhook)
            self._unhook = None
