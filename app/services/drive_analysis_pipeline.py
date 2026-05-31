"""Post-traitement des réponses IA Menu & Drive."""

from __future__ import annotations

import logging
import re
import unicodedata

from app.models.drive import CourseItem, DriveMenuAnalysisResult, RayonType

logger = logging.getLogger(__name__)

_HTML_QUOTE_PATTERN = re.compile(r'(<[^>]*)"([^>]*>)')

_RAYON_ALIASES: dict[str, RayonType] = {
    "epicerie": "Épicerie",
    "épicerie": "Épicerie",
    "frais": "Frais",
    "produits frais": "Frais",
    "fruits legumes": "Fruits & Légumes",
    "fruits & legumes": "Fruits & Légumes",
    "fruits et legumes": "Fruits & Légumes",
    "f&l": "Fruits & Légumes",
    "bebe": "Bébé",
    "bébé": "Bébé",
    "entretien": "Entretien",
    "menage": "Entretien",
    "ménage": "Entretien",
}


def sanitize_html_quotes(html_content: str) -> str:
    """Remplace \" par ' uniquement à l'intérieur des balises HTML."""
    prev = None
    current = html_content
    while prev != current:
        prev = current
        current = _HTML_QUOTE_PATTERN.sub(r"\1'\2", current)
    return current


def _normalize_rayon(value: object) -> RayonType:
    if not isinstance(value, str):
        raise ValueError(f"Rayon invalide : {value!r}")
    cleaned = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_key = cleaned.encode("ascii", "ignore").decode("ascii")
    if ascii_key in _RAYON_ALIASES:
        return _RAYON_ALIASES[ascii_key]
    if value.strip() in (
        "Épicerie",
        "Frais",
        "Fruits & Légumes",
        "Bébé",
        "Entretien",
    ):
        return value.strip()  # type: ignore[return-value]
    raise ValueError(f"Rayon non reconnu : {value!r}")


def _dedupe_courses(items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("mot_cle", "")).strip().lower()
        if not key:
            continue
        qty = int(item.get("quantite", 1))
        if key in merged:
            merged[key]["quantite"] = int(merged[key]["quantite"]) + qty
        else:
            merged[key] = dict(item)
            merged[key]["mot_cle"] = str(item["mot_cle"]).strip()
    return list(merged.values())


def finalize_drive_analysis(data: dict) -> DriveMenuAnalysisResult:
    cleaned = dict(data)
    if "planning_html" in cleaned and isinstance(cleaned["planning_html"], str):
        cleaned["planning_html"] = sanitize_html_quotes(cleaned["planning_html"])

    raw_list = cleaned.get("liste_courses", [])
    if not isinstance(raw_list, list):
        raw_list = []

    deduped = _dedupe_courses(raw_list)
    normalized_items: list[CourseItem] = []
    for item in deduped:
        item["rayon"] = _normalize_rayon(item.get("rayon", ""))
        normalized_items.append(CourseItem.model_validate(item))
    cleaned["liste_courses"] = normalized_items

    result = DriveMenuAnalysisResult.model_validate(cleaned)
    logger.info(
        "[DRIVE-IA] Planning validé — %s article(s) courses",
        len(result.liste_courses),
    )
    return result
