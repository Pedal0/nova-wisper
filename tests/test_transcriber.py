from pathlib import Path

import numpy as np
import pytest

from wisper.transcriber import Transcriber

MODEL_DIR = Path("models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8")
pytestmark = pytest.mark.skipif(
    not MODEL_DIR.exists(), reason="modele non telecharge (lancer scripts/download_model.py)"
)


def test_transcribe_known_wav_returns_text():
    import soundfile as sf
    wav = next(MODEL_DIR.glob("test_wavs/*.wav"))
    samples, sr = sf.read(wav, dtype="float32")
    t = Transcriber(str(MODEL_DIR), device="cpu")
    text = t.transcribe(samples, sample_rate=sr)
    assert isinstance(text, str)
    assert len(text.strip()) > 0


def test_transcribe_silence_returns_empty_or_short():
    t = Transcriber(str(MODEL_DIR), device="cpu")
    silence = np.zeros(16000, dtype=np.float32)  # 1s de silence
    text = t.transcribe(silence, sample_rate=16000)
    assert isinstance(text, str)
    assert len(text.strip()) <= 3  # silence -> rien (ou quasi)


def test_unload_frees_recognizer_and_transcribe_is_a_safe_noop():
    t = Transcriber(str(MODEL_DIR), device="cpu")
    assert t.loaded is True
    t.unload()
    assert t.loaded is False
    text = t.transcribe(np.ones(16000, dtype=np.float32), sample_rate=16000)
    assert text == "" 


def test_reload_after_unload_works_again():
    import soundfile as sf
    wav = next(MODEL_DIR.glob("test_wavs/*.wav"))
    samples, sr = sf.read(wav, dtype="float32")

    t = Transcriber(str(MODEL_DIR), device="cpu")
    t.unload()
    t.load()
    assert t.loaded is True
    text = t.transcribe(samples, sample_rate=sr)
    assert len(text.strip()) > 0


def test_load_is_idempotent_when_already_loaded():
    t = Transcriber(str(MODEL_DIR), device="cpu")
    recognizer_before = t._recognizer
    t.load()
    assert t._recognizer is recognizer_before
