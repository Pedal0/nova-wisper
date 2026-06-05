# tests/test_orchestrator.py
import numpy as np

from wisper.orchestrator import Orchestrator


class FakeAudio:
    def __init__(self):
        self.started = False
        self._buf = np.zeros(0, dtype=np.float32)
    def start(self): self.started = True
    def snapshot(self): return self._buf
    def stop(self):
        self.started = False
        return np.ones(16000, dtype=np.float32)  # 1s de "parole"


class FakeTranscriber:
    def transcribe(self, samples, sample_rate=16000):
        return "" if samples.size == 0 else "bonjour ceci est un test"


class FakeOverlay:
    def __init__(self):
        self.shown = False; self.hidden = False; self.texts = []
    def show(self): self.shown = True
    def update(self, t): self.texts.append(t)
    def hide(self): self.hidden = True


class FakeInjector:
    def __init__(self): self.typed = []
    def type(self, t): self.typed.append(t)


def make_orch():
    return Orchestrator(
        audio=FakeAudio(), transcriber=FakeTranscriber(),
        overlay=FakeOverlay(), injector=FakeInjector(),
        partial_interval_sec=0.05, inject_min_chars=1,
    )


def test_press_starts_capture_and_shows_overlay():
    o = make_orch()
    o.on_press()
    assert o.audio.started is True
    assert o.overlay.shown is True
    o.on_release()  # cleanup


def test_release_transcribes_hides_and_injects():
    o = make_orch()
    o.on_press()
    o.on_release()
    assert o.overlay.hidden is True
    assert o.injector.typed == ["bonjour ceci est un test"]


def test_release_without_press_does_nothing():
    o = make_orch()
    o.on_release()
    assert o.injector.typed == []


def test_empty_transcription_not_injected():
    o = make_orch()
    o.transcriber = FakeTranscriber()
    o.audio.stop = lambda: np.zeros(0, dtype=np.float32)  # buffer vide
    o.on_press()
    o.on_release()
    assert o.injector.typed == []
