from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd


class AudioCapture:
    """16kHz mono microphone capture. The callback only accumulates frames."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._capturing = False
        self._stream: sd.InputStream | None = None

    def _on_frames(self, indata: np.ndarray) -> None:
        """Called by the sounddevice callback (real-time thread)."""
        if not self._capturing:
            return
        with self._lock:
            self._frames.append(indata.reshape(-1).astype(np.float32, copy=True))

    def _callback(self, indata, frames, time, status) -> None:  # noqa: ANN001
        self._on_frames(indata)

    def snapshot(self) -> np.ndarray:
        """Copy of the accumulated buffer so far (for partial transcriptions)."""
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._frames)

    def _drain(self) -> np.ndarray:
        """Returns the full buffer and clears it."""
        with self._lock:
            buf = (
                np.concatenate(self._frames)
                if self._frames
                else np.zeros(0, dtype=np.float32)
            )
            self._frames = []
        return buf

    def start(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            self._frames = []
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            self._capturing = True
            self._stream.start()
        except Exception:
            self._capturing = False
            self._stream = None
            raise

    def stop(self) -> np.ndarray:
        """Clean stop: flag cleared + stream closed. Returns the full buffer."""
        self._capturing = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return self._drain()
