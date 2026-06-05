from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class Orchestrator:
    """State machine: IDLE → CAPTURE → FINALISE → INJECT → IDLE."""

    def __init__(
        self,
        audio,
        transcriber,
        overlay,
        injector,
        partial_interval_sec: float = 0.7,
        inject_min_chars: int = 1,
    ) -> None:
        self.audio = audio
        self.transcriber = transcriber
        self.overlay = overlay
        self.injector = injector
        self.partial_interval_sec = partial_interval_sec
        self.inject_min_chars = inject_min_chars
        self._capturing = False
        self._partial_stop = threading.Event()
        self._partial_thread: threading.Thread | None = None

    def on_press(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self.audio.start()
        self.overlay.show()
        self._partial_stop.clear()
        self._partial_thread = threading.Thread(target=self._partial_loop, daemon=True)
        self._partial_thread.start()

    def _partial_loop(self) -> None:
        last = ""
        interval = self.partial_interval_sec
        while not self._partial_stop.wait(interval):
            try:
                snap = self.audio.snapshot()
                if snap.size > 0:
                    text = self.transcriber.transcribe(snap)
                    if text and text != last:
                        last = text
                        self.overlay.update(text)
            except Exception:
                logger.exception("error in partial transcription loop")

    def on_release(self) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self._partial_stop.set()
        if self._partial_thread is not None:
            self._partial_thread.join(timeout=2.0)
            self._partial_thread = None

        full = self.transcriber.transcribe(self.audio.stop()).strip()
        self.overlay.hide()

        if len(full) >= self.inject_min_chars:
            logger.info("Injecting: %r", full)
            self.injector.type(full)
        else:
            logger.info("Empty/short transcription, nothing injected.")
