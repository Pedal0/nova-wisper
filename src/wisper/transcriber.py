from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import sherpa_onnx

logger = logging.getLogger(__name__)


class Transcriber:
    """Wraps sherpa-onnx + Parakeet-TDT.

    load()/unload() let the caller free the model's VRAM/RAM (~600MB on the
    default checkpoint) when Nova is paused, and rebuild it on resume without
    creating a new Transcriber.
    """

    def __init__(self, model_dir: str, device: str = "cpu") -> None:
        self._dir = Path(model_dir)
        self._device = device
        self._recognizer: sherpa_onnx.OfflineRecognizer | None = None
        self.load()

    @property
    def loaded(self) -> bool:
        return self._recognizer is not None

    def load(self) -> None:
        if self._recognizer is not None:
            return
        provider = "cuda" if self._device == "cuda" else "cpu"
        try:
            self._recognizer = self._build(self._dir, provider)
        except Exception:
            if provider == "cuda":
                logger.warning("CUDA provider unavailable, falling back to CPU.")
                self._recognizer = self._build(self._dir, "cpu")
            else:
                raise

    def unload(self) -> None:
        self._recognizer = None

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
        if self._recognizer is None:
            return ""
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
