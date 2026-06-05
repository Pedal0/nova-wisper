from __future__ import annotations


class TextInjector:
    """Tape du texte unicode la ou se trouve le curseur."""

    def __init__(self, controller=None) -> None:
        if controller is None:
            from pynput.keyboard import Controller
            controller = Controller()
        self._controller = controller

    def type(self, text: str) -> None:
        if not text:
            return
        self._controller.type(text)
