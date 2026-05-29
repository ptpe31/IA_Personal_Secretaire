"""Nommage GED — spec §7.1."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path


def slugify_title(title: str, max_length: int = 60) -> str:
    """Sanitize titre en slug ASCII avec underscores."""
    normalized = unicodedata.normalize("NFKD", title)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        return "Document"
    return slug[:max_length].rstrip("_")


def build_ged_filename(date_emission: date, title: str, extension: str) -> str:
    """Format : YYYY-MM-DD_Slug-Titre.ext"""
    ext = extension.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{date_emission.isoformat()}_{slugify_title(title)}{ext}"


def unique_path(directory: Path, filename: str) -> Path:
    """Évite l'écrasement en ajoutant _2, _3… si le fichier existe."""
    target = directory / filename
    if not target.exists():
        return target
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 2
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
