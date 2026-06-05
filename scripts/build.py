"""Build Nova: verify model, compile exe, assemble dist/.

Usage:
  uv run python scripts/build.py           # release build (no console window)
  uv run python scripts/build.py --debug   # debug build (console window, shows errors)
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[1]
MODELS    = ROOT / "models"
DIST      = ROOT / "dist"
SPEC      = ROOT / "Nova.spec"
CONFIG    = ROOT / "config.yaml"


def _check_models() -> bool:
    if not MODELS.exists():
        print("ERROR: models/ directory not found.")
        print("  Run first: uv run python scripts/download_model.py")
        return False
    if not list(MODELS.iterdir()):
        print("ERROR: models/ directory is empty.")
        print("  Run first: uv run python scripts/download_model.py")
        return False
    return True


def _compile(debug: bool) -> bool:
    print(f"Compiling with PyInstaller ({'debug' if debug else 'release'})...")
    cmd = ["uv", "run", "pyinstaller", "--clean"]
    if debug:
        # Override console=False from spec so errors are visible
        cmd += ["--console", "--name", "NovaDebug"]
    cmd.append(str(SPEC))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("ERROR: PyInstaller failed.")
        return False
    return True


def _copy_models(debug: bool) -> None:
    dest = DIST / "models"
    if dest.exists():
        print("Removing old dist/models/ ...")
        shutil.rmtree(dest)
    print("Copying models/ -> dist/models/ ...")
    shutil.copytree(MODELS, dest)


def _copy_config() -> None:
    dest = DIST / "config.yaml"
    shutil.copy2(CONFIG, dest)
    print("config.yaml copied to dist/")


def main() -> int:
    debug = "--debug" in sys.argv
    print(f"=== Build Nova {'[DEBUG]' if debug else ''} ===\n")

    if not _check_models():
        return 1

    if not _compile(debug):
        return 1

    _copy_models(debug)
    _copy_config()

    exe_name = "NovaDebug.exe" if debug else "Nova.exe"
    print(f"\nBuild complete!")
    print(f"  Executable : {DIST / exe_name}")
    print(f"  Models     : {DIST / 'models'}")
    print(f"  Config     : {DIST / 'config.yaml'}")
    if debug:
        print("\n  [DEBUG] A console window will open — errors will be visible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
