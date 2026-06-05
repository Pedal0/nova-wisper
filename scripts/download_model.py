"""Downloads and extracts the Parakeet-TDT v3 ONNX model into ./models/."""
import sys
import tarfile
import urllib.request
from pathlib import Path

URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2"
)
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
ARCHIVE    = MODELS_DIR / "parakeet-v3.tar.bz2"
EXTRACTED  = MODELS_DIR / "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"


def main() -> int:
    MODELS_DIR.mkdir(exist_ok=True)
    if EXTRACTED.exists():
        print(f"Model already present: {EXTRACTED}")
        return 0
    print(f"Downloading from {URL} ...")
    urllib.request.urlretrieve(URL, ARCHIVE)
    print("Extracting ...")
    with tarfile.open(ARCHIVE, "r:bz2") as tar:
        tar.extractall(MODELS_DIR)
    ARCHIVE.unlink(missing_ok=True)
    print(f"Done -> {EXTRACTED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
