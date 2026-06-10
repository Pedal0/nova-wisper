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
- **Voice notes** capture ideas hands-free with `nova note <text>`
- **App launcher** open or close any app by voice via `nova open/close <app>`
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
cd nova-wisper
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

## Voice Commands

Certain phrases are intercepted before text is injected and trigger built-in actions instead.

### Notes

Say **`nova note <your text>`** to capture an idea without injecting anything into the active window.

```
nova note call dentist tomorrow
nova note buy oat milk and bread
nova note the API key expires on the 15th
```

The note is saved instantly to `notes.json` (next to `Nova.exe`, or at the project root in dev) and the **Nova Notes** window opens automatically.

Saying **`nova note`** alone (no content) opens the notepad without saving.

The notepad lets you:
- **Copy** any note to the clipboard with one click
- **Edit** a note inline (confirm with **Ctrl+Enter**, cancel with **Escape**)
- **Delete** individual notes
- Re-open at any time via the system tray → **Notes**

### App Launcher

Say **`nova <command>`** (any phrase starting with "nova" that is not a note command) to open or close a desktop application using an LLM.

```
nova open Discord
nova close Chrome
nova lance Spotify
nova ferme le navigateur
```

Nova calls an OpenAI-compatible LLM API that interprets your intent and returns the app name and action. It works with **OpenAI**, **Ollama** (local models), and **OpenRouter**.

#### Setup

1. Open the **App Launcher** window from the system tray.
2. In **LLM Configuration**, fill in:
   - `Base URL` — e.g. `https://api.openai.com/v1` or `http://localhost:11434/v1` for Ollama
   - `API Key` — your API key (use any string for Ollama)
   - `Model` — e.g. `gpt-4o-mini` or `llama3`
3. In **Registered Apps**, add each app with its display name and full executable path. Use the **...** button to browse.
4. Click **Save** for the LLM settings, then **Add App** for each app.

Settings are stored in `launcher.json` (next to `Nova.exe`, or at the project root in dev).

#### How it works

Nova sends the voice command and the list of registered app names to the LLM. The LLM returns a JSON object:

```json
{"app_name": "Discord", "action": "open"}
```

If the model supports tool calls (OpenAI, capable Ollama models), the structured tool response is used. If not (tiny local models), Nova falls back to parsing JSON from the response text. Both paths work transparently.

- **Open:** `subprocess.Popen([path])`
- **Close:** `taskkill /f /im <exe_name>`

A brief overlay message confirms the action: *"Launching Discord..."* or *"Closing Discord..."*

If the API key is not configured or no apps are registered, the App Launcher settings window opens automatically instead of crashing.

---

## System Tray

Right-click the Nova icon in the taskbar notification area:

| Menu item | Description |
|---|---|
| **Listening: ON** | Click to disable the hotkey (no recording) |
| **Listening: OFF** | Click to re-enable the hotkey |
| **Notes** | Opens the Nova Notes window |
| **App Launcher** | Opens the App Launcher settings window |
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
│   ├── notes.py         # voice note capture + notepad UI
│   ├── launcher.py      # app launcher/closer via LLM + settings UI
│   ├── overlay/         # animated glass pill HUD
│   ├── tray.py          # system tray icon
│   ├── config.py        # configuration dataclass
│   └── logging_setup.py
├── scripts/
│   ├── build.py         # build script (PyInstaller + asset assembly)
│   └── download_model.py
├── tests/               # unit tests (pytest)
├── Nova.spec            # PyInstaller spec
└── config.yaml
```

---

## License

MIT License see [LICENSE](LICENSE) for details.

The bundled model weights (**Parakeet-TDT 0.6B v3**) are released by NVIDIA under the [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
