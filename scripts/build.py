"""Build Nova : verifie le modele, compile l'exe, assemble dist/."""
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
        print("ERREUR : dossier models/ introuvable.")
        print("  Lance d'abord : uv run python scripts/download_model.py")
        return False
    entries = list(MODELS.iterdir())
    if not entries:
        print("ERREUR : dossier models/ est vide.")
        print("  Lance d'abord : uv run python scripts/download_model.py")
        return False
    return True


def _compile() -> bool:
    print("Compilation PyInstaller...")
    result = subprocess.run(
        ["uv", "run", "pyinstaller", "--clean", str(SPEC)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("ERREUR : PyInstaller a echoue.")
        return False
    return True


def _copy_models() -> None:
    dest = DIST / "models"
    if dest.exists():
        print("Suppression de l'ancien dist/models/ ...")
        shutil.rmtree(dest)
    print(f"Copie de models/ -> dist/models/ ...")
    shutil.copytree(MODELS, dest)


def _copy_config() -> None:
    dest = DIST / "config.yaml"
    shutil.copy2(CONFIG, dest)
    print(f"config.yaml copie dans dist/")


def main() -> int:
    print("=== Build Nova ===\n")

    if not _check_models():
        return 1

    if not _compile():
        return 1

    _copy_models()
    _copy_config()

    exe = DIST / "Nova.exe"
    print(f"\nBuild termine !")
    print(f"  Executable : {exe}")
    print(f"  Modeles    : {DIST / 'models'}")
    print(f"  Config     : {DIST / 'config.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
