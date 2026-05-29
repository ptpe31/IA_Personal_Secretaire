"""Gestion Électronique des Documents — spec §7."""

from __future__ import annotations

import hashlib
import mimetypes
import shutil
from datetime import date
from pathlib import Path

from app.config import ROOT_PATH, ged_path_for_category
from app.utils.slugify import build_ged_filename, unique_path


def guess_mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime:
        return mime
    suffix = path.suffix.lower()
    if suffix == ".heic":
        return "image/heic"
    if suffix == ".pdf":
        return "application/pdf"
    return "application/octet-stream"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def move_inbox_to_ged(
    inbox_path: Path,
    *,
    category: str,
    date_emission: date,
    title: str,
) -> tuple[Path, str]:
    """
    Déplace un fichier de l'inbox vers le GED avec nommage spec.

    Returns:
        (absolute_path, relative_path depuis ROOT_PATH)
    """
    if not inbox_path.is_file():
        raise FileNotFoundError(f"Fichier inbox introuvable : {inbox_path}")

    ged_dir = ged_path_for_category(category)
    ged_dir.mkdir(parents=True, exist_ok=True)

    filename = build_ged_filename(date_emission, title, inbox_path.suffix)
    destination = unique_path(ged_dir, filename)
    shutil.move(str(inbox_path), str(destination))

    relative = destination.relative_to(ROOT_PATH).as_posix()
    return destination, relative
