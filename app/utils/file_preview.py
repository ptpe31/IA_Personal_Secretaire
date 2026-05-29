"""Utilitaires de prévisualisation et conversion de fichiers."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

from app.config import ALLOWED_EXTENSIONS

logger = logging.getLogger(__name__)

_HEIF_REGISTERED = False


def register_heif_support() -> None:
    """Enregistre le support HEIC via pillow-heif."""
    global _HEIF_REGISTERED
    if _HEIF_REGISTERED:
        return
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        _HEIF_REGISTERED = True
    except ImportError:
        logger.warning("pillow-heif non installé — fichiers HEIC non supportés.")


def is_allowed_extension(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_EXTENSIONS


def load_image_bytes_for_vision(file_path: Path) -> bytes:
    """
    Prépare les bytes image pour Ollama vision.
    PDF → page 1 PNG ; HEIC/images → PNG.
    """
    register_heif_support()
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return _pdf_first_page_to_png_bytes(file_path)

    with Image.open(file_path) as img:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()


def preview_data_url(file_path: Path) -> str | None:
    """Retourne une data URL pour affichage NiceGUI, ou None si échec."""
    try:
        png_bytes = load_image_bytes_for_vision(file_path)
        import base64

        encoded = base64.b64encode(png_bytes).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception as exc:
        logger.error("Preview impossible pour %s : %s", file_path, exc)
        return None


def _pdf_first_page_to_png_bytes(file_path: Path) -> bytes:
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError("pdf2image requis pour les PDF.") from exc

    try:
        pages = convert_from_path(str(file_path), first_page=1, last_page=1, dpi=150)
    except Exception as exc:
        raise RuntimeError(
            "Conversion PDF échouée. Installez Poppler : brew install poppler"
        ) from exc

    if not pages:
        raise RuntimeError(f"PDF vide ou illisible : {file_path.name}")

    buffer = io.BytesIO()
    pages[0].save(buffer, format="PNG")
    return buffer.getvalue()
