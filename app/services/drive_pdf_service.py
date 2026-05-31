"""Export PDF planning Menu & Drive vers la GED Perso."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app import config
from app.utils.slugify import build_ged_filename, unique_path

logger = logging.getLogger(__name__)

_WEASYPRINT_HINT = (
    "WeasyPrint nécessite les bibliothèques système Homebrew. "
    "Installez : brew install pango gdk-pixbuf libffi "
    "et lancez via start.command (DYLD_FALLBACK_LIBRARY_PATH)."
)


def save_planning_pdf(html: str, *, title: str = "Planning_Batch_Cooking") -> Path:
    """Convertit le HTML en PDF et l'enregistre dans ~/Trankil-v2/Perso/GED/."""
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError("WeasyPrint n'est pas installé (pip install weasyprint).") from exc

    ged_dir = config.PERSO_GED_PATH
    ged_dir.mkdir(parents=True, exist_ok=True)
    filename = build_ged_filename(date.today(), title, ".pdf")
    destination = unique_path(ged_dir, filename)

    try:
        HTML(string=html).write_pdf(str(destination))
    except OSError as exc:
        logger.exception("Échec WeasyPrint — bibliothèques système manquantes")
        raise RuntimeError(_WEASYPRINT_HINT) from exc

    logger.info("[DRIVE] PDF enregistré : %s", destination)
    return destination
