from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Config:
    hotkey: str = "right ctrl"
    partial_interval_sec: float = 0.7
    device: str = "cpu"
    model_dir: str = "models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
    overlay_position: str = "bottom-center"
    overlay_width: int = 220
    inject_min_chars: int = 1
    log_level: str = "INFO"


def load_config(path: str | Path) -> Config:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    known = set(Config.__dataclass_fields__)
    filtered = {k: v for k, v in data.items() if k in known}
    return Config(**filtered)
