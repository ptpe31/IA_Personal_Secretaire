"""Post-traitement des réponses IA Menu & Drive."""

from __future__ import annotations

import logging
import re
import unicodedata

from app.models.drive import (
    UNITE_MESURE_OPTIONS,
    PLANNING_JOURS,
    PLANNING_MOMENTS,
    CourseItem,
    DriveMenuAnalysisResult,
    PlanningRepasItem,
    RayonType,
    UniteMesureType,
    parse_meal_slot,
    PREMIER_JOUR_DEFAUT,
    sort_planning_repas,
)

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

_UNITE_ALIASES: dict[str, UniteMesureType] = {
    "g": "g",
    "gramme": "g",
    "grammes": "g",
    "kg": "kg",
    "kilogramme": "kg",
    "kilogrammes": "kg",
    "ml": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "l": "L",
    "litre": "L",
    "litres": "L",
    "u": "u",
    "unite": "u",
    "unité": "u",
    "unites": "u",
    "unités": "u",
    "piece": "u",
    "pièce": "u",
    "pieces": "u",
    "pièces": "u",
    "oeuf": "u",
    "oeufs": "u",
    "tranche": "u",
    "tranches": "u",
}

_JOUR_ALIASES: dict[str, str] = {j.lower(): j for j in PLANNING_JOURS}
_MOMENT_ALIASES: dict[str, str] = {
    "midi": "Midi",
    "déjeuner": "Midi",
    "dejeuner": "Midi",
    "soir": "Soir",
    "dîner": "Soir",
    "diner": "Soir",
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


def _normalize_unite(value: object, *, default: UniteMesureType = "u") -> UniteMesureType:
    if not isinstance(value, str):
        return default
    cleaned = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_key = cleaned.encode("ascii", "ignore").decode("ascii")
    if ascii_key in _UNITE_ALIASES:
        return _UNITE_ALIASES[ascii_key]
    if value.strip() in UNITE_MESURE_OPTIONS:
        return value.strip()  # type: ignore[return-value]
    return default


_QTY_PREFIX_RE = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*(g|kg|ml|m?l|L|u|unités?|unites?|pièces?|pieces?|oeufs?)\s+",
    re.IGNORECASE,
)


def strip_quantity_from_text(
    text: str,
    *,
    quantite: float | None = None,
    unite: str | None = None,
) -> str:
    """Retire les quantités en tête de chaîne (ex. « 600 g épinards » → « épinards »)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned

    if quantite is not None and unite:
        qty_label = str(int(quantite)) if quantite == int(quantite) else str(quantite)
        for prefix in (
            f"{qty_label} {unite}",
            f"{qty_label}{unite}",
            f"{qty_label.replace('.', ',')} {unite}",
        ):
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :].strip()
                break

    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        match = _QTY_PREFIX_RE.match(cleaned)
        if match:
            cleaned = cleaned[match.end() :].strip()
    return cleaned.strip() or (text or "").strip()


def truncate_to_max_words(text: str, max_words: int = 3) -> str:
    """Limite un libellé IA à N mots (espaces)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned
    return " ".join(words[:max_words])


def _clean_product_label(
    raw: str,
    *,
    quantite: float,
    unite: UniteMesureType,
    fallback: str,
) -> str:
    cleaned = strip_quantity_from_text(raw, quantite=quantite, unite=unite)
    if not cleaned:
        return fallback
    return cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()


def _normalize_jour(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Jour invalide : {value!r}")
    cleaned = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_key = cleaned.encode("ascii", "ignore").decode("ascii")
    if ascii_key in _JOUR_ALIASES:
        return _JOUR_ALIASES[ascii_key]
    if value.strip() in PLANNING_JOURS:
        return value.strip()
    raise ValueError(f"Jour non reconnu : {value!r}")


def _normalize_moment(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Moment invalide : {value!r}")
    cleaned = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_key = cleaned.encode("ascii", "ignore").decode("ascii")
    if ascii_key in _MOMENT_ALIASES:
        return _MOMENT_ALIASES[ascii_key]
    if value.strip() in PLANNING_MOMENTS:
        return value.strip()
    raise ValueError(f"Moment non reconnu : {value!r}")


def _normalize_planning_raw(item: dict) -> dict | None:
    plat = str(item.get("plat", "")).strip()
    if not plat:
        return None
    batch = str(
        item.get("batch_cooking_dimanche")
        or item.get("batch_cooking")
        or item.get("batch_dimanche")
        or ""
    ).strip()
    action = str(
        item.get("action_minute") or item.get("action_jour") or item.get("action") or ""
    ).strip()
    if not batch:
        batch = "—"
    if not action:
        action = "—"
    return {
        "jour": _normalize_jour(item.get("jour", "")),
        "moment": _normalize_moment(item.get("moment", "")),
        "plat": plat,
        "batch_cooking_dimanche": batch,
        "action_minute": action,
    }


def _normalize_course_raw(item: dict) -> dict | None:
    mot_cle = str(item.get("mot_cle", "")).strip()
    if not mot_cle:
        return None
    normalized = dict(item)
    normalized["mot_cle"] = mot_cle

    if "quantite_recette" not in normalized:
        if "quantite_besoin" in normalized:
            normalized["quantite_recette"] = float(normalized.pop("quantite_besoin"))
        elif "quantite" in normalized:
            normalized["quantite_recette"] = float(normalized.pop("quantite"))
        else:
            normalized["quantite_recette"] = 1.0

    if "unite_recette" not in normalized:
        raw_unite = normalized.pop("unite", None) or normalized.pop("unite_besoin", None)
        normalized["unite_recette"] = _normalize_unite(raw_unite or "u")

    if "libelle" not in normalized:
        normalized["libelle"] = mot_cle

    normalized["quantite_recette"] = max(0.01, float(normalized["quantite_recette"]))
    normalized["unite_recette"] = _normalize_unite(normalized["unite_recette"])
    qty = float(normalized["quantite_recette"])
    unite = normalized["unite_recette"]
    normalized["mot_cle"] = truncate_to_max_words(
        strip_quantity_from_text(
            normalized["mot_cle"], quantite=qty, unite=unite
        ).lower(),
        max_words=3,
    )
    normalized["libelle"] = truncate_to_max_words(
        _clean_product_label(
            str(normalized.get("libelle") or normalized["mot_cle"]),
            quantite=qty,
            unite=unite,
            fallback=normalized["mot_cle"],
        ),
        max_words=3,
    )
    return normalized


def _dedupe_courses(items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_course_raw(item)
        if normalized is None:
            continue
        unite = normalized["unite_recette"]
        key = f"{normalized['mot_cle'].strip().lower()}::{unite}"
        qty = float(normalized["quantite_recette"])
        if key in merged:
            merged[key]["quantite_recette"] = float(merged[key]["quantite_recette"]) + qty
        else:
            merged[key] = normalized
    return list(merged.values())


def _allowed_planning_slots(input_plats: dict[str, str]) -> set[tuple[str, str]]:
    allowed: set[tuple[str, str]] = set()
    for slot in input_plats:
        try:
            allowed.add(parse_meal_slot(slot))
        except ValueError:
            logger.warning("[DRIVE-IA] Créneau plat ignoré pour filtre : %s", slot)
    return allowed


def filter_planning_to_allowed_slots(
    items: list[PlanningRepasItem],
    allowed_slots: set[tuple[str, str]] | None,
) -> list[PlanningRepasItem]:
    """Retire les repas inventés par l'IA hors créneaux autorisés."""
    if not allowed_slots:
        return items
    kept = [item for item in items if (item.jour, item.moment) in allowed_slots]
    dropped = len(items) - len(kept)
    if dropped:
        logger.warning(
            "[DRIVE-IA] %s créneau(x) inventé(s) par l'IA ignoré(s) (hors créneaux autorisés)",
            dropped,
        )
    return kept


def filter_planning_to_input(
    items: list[PlanningRepasItem],
    input_plats: dict[str, str] | None,
) -> list[PlanningRepasItem]:
    """Retire les repas inventés par l'IA hors créneaux saisis (compatibilité)."""
    if not input_plats:
        return items
    allowed = _allowed_planning_slots(input_plats)
    return filter_planning_to_allowed_slots(items, allowed or None)


def finalize_drive_analysis(
    data: dict,
    *,
    allowed_slots: set[tuple[str, str]] | None = None,
    allowed_regime_slots: set[tuple[str, str]] | None = None,
    input_plats: dict[str, str] | None = None,
    premier_jour_semaine: str = PREMIER_JOUR_DEFAUT,
) -> DriveMenuAnalysisResult:
    cleaned = dict(data)

    raw_planning = cleaned.get("planning_repas", [])
    if not isinstance(raw_planning, list):
        raw_planning = []
    planning_items: list[PlanningRepasItem] = []
    for item in raw_planning:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_planning_raw(item)
        if normalized is None:
            continue
        planning_items.append(PlanningRepasItem.model_validate(normalized))

    if allowed_slots is None and input_plats:
        allowed_slots = _allowed_planning_slots(input_plats) or None
    planning_items = filter_planning_to_allowed_slots(planning_items, allowed_slots)
    if allowed_slots and not planning_items:
        raise ValueError(
            "planning_repas vide ou invalide — aucun créneau enfant ne correspond à la saisie utilisateur."
        )
    cleaned["planning_repas"] = sort_planning_repas(
        planning_items, premier_jour=premier_jour_semaine
    )

    raw_regime = cleaned.get("planning_regime", [])
    if not isinstance(raw_regime, list):
        raw_regime = []
    regime_items: list[PlanningRepasItem] = []
    for item in raw_regime:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_planning_raw(item)
        if normalized is None:
            continue
        regime_items.append(PlanningRepasItem.model_validate(normalized))

    regime_items = filter_planning_to_allowed_slots(regime_items, allowed_regime_slots)
    if allowed_regime_slots and not regime_items:
        raise ValueError(
            "planning_regime vide ou invalide — aucun créneau hôte régime ne correspond à la saisie utilisateur."
        )
    cleaned["planning_regime"] = sort_planning_repas(
        regime_items, premier_jour=premier_jour_semaine
    )

    if not cleaned["planning_repas"] and not cleaned["planning_regime"]:
        raise ValueError(
            "planning_repas et planning_regime vides — aucun créneau ne correspond à la saisie utilisateur."
        )

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
        "[DRIVE-IA] Planning validé — %s repas enfants, %s repas hôte régime, %s article(s) courses",
        len(result.planning_repas),
        len(result.planning_regime),
        len(result.liste_courses),
    )
    return result
