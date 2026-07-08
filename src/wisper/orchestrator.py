from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable

import numpy as np

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
        realtime_typing: bool = True,
        silence_sec: float = 0.6,
        silence_threshold: float = 0.01,
        max_chunk_sec: float = 12.0,
        sample_rate: int = 16000,
    ) -> None:
        self.audio = audio
        self.transcriber = transcriber
        self.overlay = overlay
        self.injector = injector
        self.partial_interval_sec = partial_interval_sec
        self.inject_min_chars = inject_min_chars
        self.note_callback = note_callback
        self.app_callback = app_callback
        self.realtime_typing = realtime_typing
        self.silence_sec = silence_sec
        self.silence_threshold = silence_threshold
        self.max_chunk_sec = max_chunk_sec
        self.sample_rate = sample_rate
        self._capturing = False
        self._partial_stop = threading.Event()
        self._partial_thread: threading.Thread | None = None
        self._offset = 0          # samples already transcribed and dropped
        self._committed = ""      # transcribed chunks, buffered until key release
        self._last_partial = ""

    def on_press(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self._offset = 0
        self._committed = ""
        self._last_partial = ""
        self.audio.start()
        self.overlay.show()
        self._partial_stop.clear()
        self._partial_thread = threading.Thread(target=self._partial_loop, daemon=True)
        self._partial_thread.start()

    def _partial_loop(self) -> None:
        while not self._partial_stop.wait(self.partial_interval_sec):
            try:
                self._tick_partial()
            except Exception:
                logger.exception("error in partial transcription loop")

    def _tick_partial(self) -> None:
        """One partial pass: either close a chunk, or refresh the preview.

        Chunks bounded by silence (or force-split when too long) are
        transcribed once, buffered, and their audio dropped — decodes stay
        short no matter how long the dictation runs.  Nothing is typed until
        the key is released; the overlay is the live preview.
        """
        seg = self.audio.snapshot()[self._offset:]
        if seg.size == 0:
            return

        if self.realtime_typing:
            n_sil = int(self.sample_rate * self.silence_sec)
            if (
                seg.size > n_sil + self.sample_rate // 2
                and float(np.sqrt(np.mean(seg[-n_sil:] ** 2))) < self.silence_threshold
            ):
                self._commit_chunk(seg, seg.size)
                return

            # No pause for too long: force a split at the quietest point —
            # long windows lag AND make the multilingual model drift to the
            # wrong language.
            if seg.size > int(self.sample_rate * self.max_chunk_sec):
                self._commit_chunk(seg, self._quietest_split(seg))
                return

        text = self.transcriber.transcribe(seg)
        if text and text != self._last_partial:
            self._last_partial = text
            self._preview(text)

    def _commit_chunk(self, seg: np.ndarray, split: int) -> None:
        """Transcribe seg[:split], buffer the text, drop that audio."""
        text = self.transcriber.transcribe(seg[:split]).strip()
        self._offset += split
        if text:
            self._committed += (" " if self._committed else "") + text
            logger.info("Chunk buffered: %r", text)
            self._last_partial = ""
            self.overlay.update(self._committed)

    def _preview(self, text: str) -> None:
        """Overlay shows buffered chunks + the live, self-correcting tail."""
        if self._committed:
            text = self._committed + " " + text
        self.overlay.update(text)

    def _quietest_split(self, seg: np.ndarray) -> int:
        """Sample index of the lowest-energy ~0.25s window in the middle of seg.

        ponytail: coarse hop scan — a breath between words is enough of a dip;
        if speech is truly continuous the cut may land mid-word.
        """
        win = int(self.sample_rate * 0.25)
        lo = int(seg.size * 0.3)
        hi = int(seg.size * 0.9) - win
        best, best_rms = seg.size, float("inf")
        for s in range(lo, max(hi, lo + 1), win // 2):
            rms = float(np.sqrt(np.mean(seg[s:s + win] ** 2)))
            if rms < best_rms:
                best_rms, best = rms, s + win // 2
        return best

    def on_release(self) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self._partial_stop.set()
        if self._partial_thread is not None:
            self._partial_thread.join(timeout=2.0)
            self._partial_thread = None

        samples = self.audio.stop()
        tail = self.transcriber.transcribe(samples[self._offset:]).strip()
        self.overlay.hide()

        # Buffered chunks + final tail = the whole utterance, injected (or
        # routed) in one clean shot.
        full = self._committed + (" " if self._committed and tail else "") + tail

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
