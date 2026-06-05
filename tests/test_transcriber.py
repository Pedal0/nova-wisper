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
