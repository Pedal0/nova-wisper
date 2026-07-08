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


# ── Découpage en chunks (silence / longueur max) ─────────────────────────────

def speech_then_silence(speech_sec=2.0, silence_sec=0.8):
    """2s de 'parole' (bruit) suivie d'un silence qui clôt le chunk."""
    rng = np.random.default_rng(0)
    speech = (rng.standard_normal(int(16000 * speech_sec)) * 0.3).astype(np.float32)
    silence = np.zeros(int(16000 * silence_sec), dtype=np.float32)
    return np.concatenate([speech, silence])


def make_rt_orch(text="bonjour tout le monde", app_callback=None, extra_tail=None):
    buf = speech_then_silence()
    stop_buf = np.concatenate([buf, extra_tail]) if extra_tail is not None else buf

    class Audio(FakeAudio):
        def snapshot(self):
            return buf
        def stop(self):
            return stop_buf

    class Tr:
        def transcribe(self, samples, sample_rate=16000):
            return "" if samples.size == 0 else text

    o = Orchestrator(
        audio=Audio(), transcriber=Tr(),
        overlay=FakeOverlay(), injector=FakeInjector(),
        partial_interval_sec=0.05, app_callback=app_callback,
    )
    o._capturing = True  # simule on_press sans thread
    return o


def test_silence_bounded_chunk_is_buffered_not_typed():
    o = make_rt_orch()
    o._tick_partial()
    assert o.injector.typed == []      # rien tapé pendant la dictée
    assert o._committed == "bonjour tout le monde"
    assert o._offset > 0               # audio du chunk retiré de la fenêtre


def test_release_types_chunks_plus_tail_in_one_shot():
    extra = np.ones(16000, dtype=np.float32)  # 1s de parole après le chunk
    o = make_rt_orch(extra_tail=extra)
    o._tick_partial()          # chunk bufferisé, offset = fin du snapshot
    o.on_release()
    assert o.injector.typed == ["bonjour tout le monde bonjour tout le monde"]


def test_release_after_chunk_with_empty_tail():
    o = make_rt_orch()
    o._tick_partial()
    o.on_release()             # tail vide → juste le chunk
    assert o.injector.typed == ["bonjour tout le monde"]


def test_nova_command_routed_even_when_chunked():
    calls = []
    o = make_rt_orch(text="nova open discord", app_callback=calls.append)
    o._tick_partial()          # la commande part dans le buffer de chunks
    assert o.injector.typed == []
    o.on_release()
    assert calls == ["nova open discord"]
    assert o.injector.typed == []


def test_long_speech_without_pause_is_force_split():
    rng = np.random.default_rng(1)
    speech = (rng.standard_normal(16000 * 14) * 0.3).astype(np.float32)
    dip_at = 16000 * 7
    speech[dip_at:dip_at + 8000] = 0.0  # respiration au milieu

    class Audio(FakeAudio):
        def snapshot(self):
            return speech
        def stop(self):
            return speech

    class Tr:
        def transcribe(self, samples, sample_rate=16000):
            return "" if samples.size == 0 else "premiere partie"

    o = Orchestrator(
        audio=Audio(), transcriber=Tr(),
        overlay=FakeOverlay(), injector=FakeInjector(),
        max_chunk_sec=12.0,
    )
    o._capturing = True
    o._tick_partial()
    assert o.injector.typed == []
    assert o._committed == "premiere partie"
    # coupe dans la respiration (7s-7.5s), pas au bord
    assert abs(o._offset - (dip_at + 4000)) < 8000


def test_realtime_disabled_keeps_single_final_injection():
    o = make_rt_orch()
    o.realtime_typing = False
    o._tick_partial()
    assert o.injector.typed == []
    o.on_release()
    assert o.injector.typed == ["bonjour tout le monde"]
