from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Matches "nova note [optional content]" as the entire transcription.
# "note?" makes the trailing 'e' optional to catch ASR misrecognitions like
# "Nova Not" instead of "Nova note".  "s?" additionally accepts "notes".
# Examples that match:
#   "nova note buy milk"       → group(1) = "buy milk"   (save + open)
#   "Nova note, call dentist"  → group(1) = "call dentist"
#   "Nova Not buy milk"        → group(1) = "buy milk"   (ASR variant)
#   "nova notes"               → group(1) = None          (open notepad only)
#   "nova note"                → group(1) = None
# "nova notebook" does NOT match ("book" cannot follow without a space/comma).
_NOTE_RE = re.compile(
    r"^nova[,\s]*note?s?(?:[,\s]+(.+))?$",
    re.IGNORECASE | re.DOTALL,
)

# Matches any utterance that begins with the word "nova" — used to route
# voice commands to the app launcher when the note trigger didn't fire.
# Examples: "nova open discord", "nova ferme chrome", "nova launch spotify"
_NOVA_PREFIX_RE = re.compile(r"^nova\b", re.IGNORECASE)


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
        note_callback: Callable[[str | None], None] | None = None,
        app_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.audio = audio
        self.transcriber = transcriber
        self.overlay = overlay
        self.injector = injector
        self.partial_interval_sec = partial_interval_sec
        self.inject_min_chars = inject_min_chars
        self.note_callback = note_callback
        self.app_callback = app_callback
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

        # ── Command routing ────────────────────────────────────────────────────
        # Strip trailing punctuation: the ASR often appends "." or "," at the
        # end (e.g. "Nova note." / "Nova open discord."), which would break
        # end-anchored regex matches.  We only strip for routing; `full` is
        # left intact for text injection below.
        cleaned = full.rstrip(" .,!?;:")

        # 1. Note trigger — must be checked FIRST so "nova note" never reaches
        #    the app launcher.
        if self.note_callback:
            m = _NOTE_RE.match(cleaned)
            if m is not None:
                content = (m.group(1) or "").strip() or None
                logger.info("Note trigger: %r", content)
                self.note_callback(content)
                return

        # 2. App launcher trigger — any other "nova …" phrase.
        if self.app_callback and _NOVA_PREFIX_RE.match(cleaned):
            logger.info("App launcher trigger: %r", full)
            self.app_callback(full)
            return

        if len(full) >= self.inject_min_chars:
            logger.info("Injecting: %r", full)
            self.injector.type(full)
        else:
            logger.info("Empty/short transcription, nothing injected.")
