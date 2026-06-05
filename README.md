# Nova Local Push-to-Talk Dictation

**Nova** is a lightweight Windows desktop app that transcribes your voice and types the result wherever your cursor is. Hold a key, speak, release the text appears. No cloud, no subscription, no internet required.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Model](https://img.shields.io/badge/model-Parakeet--TDT%200.6B%20v3-orange)

---

## Overview

Nova runs entirely offline using NVIDIA's **Parakeet-TDT 0.6B v3** model quantized to INT8 via [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx). It integrates into Windows as a system tray app with a glass pill HUD that animates when you speak.

**Key capabilities:**

- **Push-to-talk** hold Right Ctrl to record, release to inject
- **Real-time preview** partial transcription displayed in the overlay while you speak
- **Universal injection** types into any focused window via `SendInput`
- **Offline** the model runs locally, nothing leaves your machine
- **System tray** toggle listening on/off or quit from the taskbar icon

---

## Requirements

| Component | Minimum |
|---|---|
| OS | Windows 10 / 11 (64-bit) |
| Python | 3.11+ (dev only) |
| RAM | 2 GB free |
| Disk | ~500 MB (model) |
| Microphone | Any input device |

> **Note:** Nova injects text using `SendInput`. It cannot type into windows running with administrator privileges unless Nova itself is also run as administrator.

---

## Model

Nova uses the **sherpa-onnx Parakeet-TDT 0.6B v3 INT8** model a quantized export of NVIDIA's [parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) optimized for CPU inference.

| Property | Value |
|---|---|
| Architecture | FastConformer-TDT |
| Parameters | 600M (INT8 quantized) |
| Sample rate | 16 kHz mono |
| Languages | English + 24 European languages |
| Inference | sherpa-onnx (ONNX Runtime) |

---

## Setup (Development)

### 1. Clone the repository

```bash
git clone https://github.com/Pedal0/nova-wisper.git
cd nova
```

### 2. Install dependencies

Nova uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
pip install uv
uv sync --extra dev
```

> `--extra dev` installs PyInstaller alongside the runtime dependencies. Omit it if you only want to run Nova without building the executable.

### 3. Download the model

```bash
uv run python scripts/download_model.py
```

This downloads and extracts the model (~500 MB) into `models/`:

```
models/
└── sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/
    ├── encoder.int8.onnx
    ├── decoder.int8.onnx
    ├── joiner.int8.onnx
    └── tokens.txt
```

> **Alternatively**, download the archive manually from the [sherpa-onnx releases](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models) and extract it into the `models/` folder at the project root.

### 4. Run in development

```bash
uv run python src/wisper/app.py
```

---

## Build

The build script checks for the model, compiles the executable with PyInstaller, and assembles the final `dist/` folder.

```bash
uv run python scripts/build.py
```

**Output:**

```
dist/
├── Nova.exe          ← standalone executable
├── config.yaml       ← user-editable settings
└── models/           ← copied from project root
    └── sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/
```

> If `models/` is missing, the script exits with an error and tells you to run `download_model.py` first.

To distribute Nova, copy the entire `dist/` folder. No installer needed.

---

## Usage

Launch `Nova.exe` (or `uv run python src/wisper/app.py` in dev). A blue icon appears in the system tray.

| Action | Result |
|---|---|
| Hold **Right Ctrl** | Starts recording, pill overlay appears |
| Speak | Partial transcription shown in real time |
| Release **Right Ctrl** | Final transcription injected at cursor position |

The hotkey can be changed in `config.yaml` (see [Configuration](#configuration)).

---

## System Tray

Right-click the Nova icon in the taskbar notification area:

| Menu item | Description |
|---|---|
| **Listening: ON** | Click to disable the hotkey (no recording) |
| **Listening: OFF** | Click to re-enable the hotkey |
| **Quit** | Closes Nova |

---

## Configuration

Edit `config.yaml` (next to `Nova.exe`, or at the project root in dev) to customize behavior. Changes take effect on next launch.

```yaml
hotkey: "right ctrl"        # push-to-talk key (hold to record)
partial_interval_sec: 0.7   # partial transcription refresh rate (seconds)
device: "cpu"               # "cpu" | "cuda"
model_dir: "models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
overlay_width: 220          # width of the pill HUD in pixels
inject_min_chars: 1         # minimum characters required to inject text
log_level: "INFO"           # "DEBUG" | "INFO" | "WARNING"
```

**CUDA support:** Set `device: "cuda"` if you have a compatible NVIDIA GPU and the CUDA-enabled sherpa-onnx package installed. Nova falls back to CPU automatically if CUDA is unavailable.

---

## Project Structure

```
nova/
├── src/wisper/
│   ├── app.py           # entry point
│   ├── orchestrator.py  # state machine: IDLE → CAPTURE → INJECT
│   ├── audio_capture.py # microphone recording
│   ├── transcriber.py   # sherpa-onnx wrapper
│   ├── injector.py      # text injection via pynput
│   ├── hotkey.py        # push-to-talk key listener
│   ├── overlay/         # animated glass pill HUD
│   ├── tray.py          # system tray icon
│   ├── config.py        # configuration dataclass
│   └── logging_setup.py
├── scripts/
│   ├── build.py         # build script (PyInstaller + asset assembly)
│   └── download_model.py
├── tests/
├── Nova.spec            # PyInstaller spec
└── config.yaml
```

---

## License

MIT License see [LICENSE](LICENSE) for details.

The bundled model weights (**Parakeet-TDT 0.6B v3**) are released by NVIDIA under the [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
