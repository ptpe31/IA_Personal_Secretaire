"""Ingestion de fichiers Inbox — pipeline partagé upload / collage."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.config import INBOX_PATH

PASTE_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heic",
}


def extension_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix else ".png"


def is_paste_mime_allowed(mime: str) -> bool:
    return mime.lower().startswith("image/")


def build_inbox_destination(filename: str) -> Path:
    """Chemin unique dans ~/.inbox pour un nouveau document."""
    safe_name = Path(filename).name or "document.png"
    inbox_name = f"{uuid.uuid4().hex}_{safe_name}"
    INBOX_PATH.mkdir(parents=True, exist_ok=True)
    return INBOX_PATH / inbox_name


def build_paste_filename(mime: str) -> str:
    ext = PASTE_MIME_TO_EXT.get(mime.lower(), ".png")
    return f"paste_{uuid.uuid4().hex[:8]}{ext}"
