"""Utilitaires macOS — ouverture Finder."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def reveal_in_finder(path: Path) -> None:
    """Révèle un fichier dans le Finder (macOS)."""
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    if sys.platform != "darwin":
        raise RuntimeError("L'ouverture Finder n'est disponible que sur macOS.")
    subprocess.run(["open", "-R", str(path.resolve())], check=False)


def open_file(path: Path) -> None:
    """Ouvre un fichier avec l'application par défaut."""
    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    if sys.platform != "darwin":
        raise RuntimeError("Ouverture native disponible uniquement sur macOS.")
    subprocess.run(["open", str(path.resolve())], check=False)
