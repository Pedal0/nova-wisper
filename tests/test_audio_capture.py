import numpy as np

from wisper.audio_capture import AudioCapture


def test_frames_accumulate_in_buffer():
    cap = AudioCapture(sample_rate=16000)
    cap._capturing = True
    cap._on_frames(np.ones((100, 1), dtype=np.float32))
    cap._on_frames(np.ones((50, 1), dtype=np.float32))
    snap = cap.snapshot()
    assert snap.shape == (150,)
    assert snap.dtype == np.float32


def test_stop_returns_full_buffer_and_resets_flag():
    cap = AudioCapture(sample_rate=16000)
    cap._capturing = True
    cap._on_frames(np.ones((200, 1), dtype=np.float32))
    full = cap._drain()  # logique de stop sans vrai stream
    assert full.shape == (200,)
    # apres drain, un nouveau snapshot repart a zero
    assert cap.snapshot().shape == (0,)


def test_frames_ignored_when_not_capturing():
    cap = AudioCapture(sample_rate=16000)
    cap._capturing = False
    cap._on_frames(np.ones((100, 1), dtype=np.float32))
    assert cap.snapshot().shape == (0,)
