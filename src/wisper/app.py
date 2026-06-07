from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

# Windows: preload sherpa-onnx's bundled onnxruntime.dll before importing any
# wisper module. C:\Windows\System32\onnxruntime.dll (v1.17, Windows AI
# component) otherwise shadows sherpa-onnx's v1.24, causing a fatal API
# version mismatch. Loading by full path first registers the module name in
# the process DLL cache; sherpa-onnx's C extension then reuses it.
if sys.platform == "win32":
    def _preload_ort() -> None:
        import ctypes, importlib.util, os
        if getattr(sys, "frozen", False):
            p = os.path.join(sys._MEIPASS, "onnxruntime.dll")
        else:
            s = importlib.util.find_spec("sherpa_onnx")
            p = os.path.join(os.path.dirname(s.origin), "lib", "onnxruntime.dll") if s else ""
        if p and os.path.exists(p):
            ctypes.CDLL(p)
    _preload_ort()
    del _preload_ort

from wisper.audio_capture import AudioCapture
from wisper.config import Config, load_config
from wisper.hotkey import HotkeyListener
from wisper.injector import TextInjector
from wisper.logging_setup import setup_logging
from wisper.notes import NoteManager
from wisper.orchestrator import Orchestrator
from wisper.overlay import OverlayHUD
from wisper.transcriber import Transcriber

logger = logging.getLogger(__name__)


def _root() -> Path:
    """Project root: exe directory (frozen) or working directory (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def main() -> int:
    cfg_path = _root() / "config.yaml"
    cfg = load_config(cfg_path) if cfg_path.exists() else Config()
    setup_logging(cfg.log_level)

    model_dir = _root() / cfg.model_dir
    if not model_dir.exists():
        logger.error(
            "Model not found: %s — run: uv run python scripts/download_model.py",
            model_dir,
        )
        return 1

    logger.info("Loading model (%s)...", cfg.device)
    transcriber = Transcriber(str(model_dir), device=cfg.device)
    audio = AudioCapture(sample_rate=16000)
    injector = TextInjector()
    overlay = OverlayHUD(width=cfg.overlay_width)

    # overlay.schedule() safely no-ops if the tk root isn't ready yet.
    # Actual UI calls only happen after overlay.create_window() (below), so the
    # ordering here is safe.
    notes = NoteManager(
        schedule_ui=overlay.schedule,
        data_path=_root() / "notes.json",
    )

    orch = Orchestrator(
        audio=audio,
        transcriber=transcriber,
        overlay=overlay,
        injector=injector,
        partial_interval_sec=cfg.partial_interval_sec,
        inject_min_chars=cfg.inject_min_chars,
        note_callback=notes.on_note,
    )

    listening = True

    def guarded_press() -> None:
        if listening:
            orch.on_press()

    def guarded_release() -> None:
        if listening:
            orch.on_release()

    hotkey = HotkeyListener(cfg.hotkey, on_press=guarded_press, on_release=guarded_release)

    from wisper.tray import TrayApp

    def on_toggle(state: bool) -> None:
        nonlocal listening
        listening = state
        logger.info("Listening %s", "enabled" if state else "disabled")

    def on_quit() -> None:
        hotkey.stop()
        overlay.close()

    tray = TrayApp(on_toggle=on_toggle, on_quit=on_quit, on_notes=notes.open_window)
    overlay.create_window()

    def _start_background() -> None:
        hotkey.start()
        tray.run_detached()
        logger.info("Nova ready. Hold '%s' to dictate.", cfg.hotkey)

    threading.Thread(target=_start_background, daemon=True).start()
    overlay.start()
    hotkey.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
