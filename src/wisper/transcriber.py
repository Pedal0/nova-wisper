from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import sherpa_onnx

logger = logging.getLogger(__name__)


class Transcriber:
    """Wraps sherpa-onnx + Parakeet-TDT. Creates the recognizer once."""

    def __init__(self, model_dir: str, device: str = "cpu") -> None:
        d = Path(model_dir)
        provider = "cuda" if device == "cuda" else "cpu"
        try:
            self._recognizer = self._build(d, provider)
        except Exception:
            if provider == "cuda":
                logger.warning("CUDA provider unavailable, falling back to CPU.")
                self._recognizer = self._build(d, "cpu")
            else:
                raise

    @staticmethod
    def _build(model_dir: Path, provider: str) -> sherpa_onnx.OfflineRecognizer:
        return sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(model_dir / "encoder.int8.onnx"),
            decoder=str(model_dir / "decoder.int8.onnx"),
            joiner=str(model_dir / "joiner.int8.onnx"),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=2,
            model_type="nemo_transducer",
            decoding_method="greedy_search",
            provider=provider,
        )

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        """samples: float32 mono in [-1, 1]. Returns the text (may be empty)."""
        if samples.ndim > 1:
            samples = samples.reshape(-1)
        samples = np.ascontiguousarray(samples, dtype=np.float32)
        # Model requires at least ~0.5s of audio, otherwise shape {0,128} → RuntimeError
        if samples.size < sample_rate // 2:
            return ""
        stream = self._recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        self._recognizer.decode_stream(stream)
        return stream.result.text or ""
