"""Modèles Menu & Drive — planning batch cooking + liste courses."""

from __future__ import annotations

import html as html_module
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.utils.dates import compute_menu_week_sunday

RayonType = Literal["Épicerie", "Frais", "Fruits & Légumes", "Bébé", "Entretien"]
UniteMesureType = Literal["g", "kg", "ml", "L", "u"]
DrivePlatformId = Literal["leclerc", "auchan", "carrefour"]
PlanningJourType = Literal[
    "Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"
]
PlanningMomentType = Literal["Midi", "Soir"]

UNITE_MESURE_OPTIONS: list[UniteMesureType] = ["g", "kg", "ml", "L", "u"]

DRIVE_PLATFORMS: dict[DrivePlatformId, dict[str, Any]] = {
    "leclerc": {
        "label": "Leclerc Drive",
        "robot_label": "LANCER LE ROBOT LECLERC DRIVE",
        "available": True,
    },
    "auchan": {
        "label": "Auchan Drive (Bientôt)",
        "robot_label": "LANCER LE ROBOT AUCHAN DRIVE",
        "available": False,
    },
    "carrefour": {
        "label": "Carrefour Drive (Bientôt)",
        "robot_label": "LANCER LE ROBOT CARREFOUR DRIVE",
        "available": False,
    },
}

DEFAULT_DRIVE_PLATFORM: DrivePlatformId = "leclerc"
DRIVE_PLATFORM_SELECT_OPTIONS: list[str] = [
    cfg["label"] for cfg in DRIVE_PLATFORMS.values()
]

RAYON_ORDER: tuple[RayonType, ...] = (
    "Épicerie",
    "Frais",
    "Fruits & Légumes",
    "Bébé",
    "Entretien",
)

JOURS_ORDRE_ABSOLU: tuple[PlanningJourType, ...] = (
    "Lundi",
    "Mardi",
    "Mercredi",
    "Jeudi",
    "Vendredi",
    "Samedi",
    "Dimanche",
)
PREMIER_JOUR_DEFAUT: PlanningJourType = "Lundi"

MEAL_SLOTS: tuple[str, ...] = (
    "Dimanche midi",
    "Dimanche soir",
    "Lundi midi",
    "Lundi soir",
    "Mardi midi",
    "Mardi soir",
    "Mercredi midi",
    "Mercredi soir",
    "Jeudi midi",
    "Jeudi soir",
    "Vendredi midi",
    "Vendredi soir",
    "Samedi midi",
    "Samedi soir",
)

REGIME_DAYS: tuple[str, ...] = (
    "Lundi",
    "Mardi",
    "Mercredi",
    "Jeudi",
    "Vendredi",
    "Samedi",
    "Dimanche",
)


MEAL_PREFIXES: dict[str, str] = {slot: f"{slot} : " for slot in MEAL_SLOTS}


def parse_meal_slot(slot: str) -> tuple[PlanningJourType, PlanningMomentType]:
    """Convertit « Mardi soir » → (« Mardi », « Soir »)."""
    lower = slot.strip().lower()
    for moment in PLANNING_MOMENTS:
        suffix = f" {moment.lower()}"
        if lower.endswith(suffix):
            jour_raw = slot[: -len(suffix)].strip()
            if jour_raw in PLANNING_JOURS:
                return jour_raw, moment  # type: ignore[return-value]
            break
    raise ValueError(f"Créneau repas invalide : {slot!r}")
REGIME_PREFIXES: dict[str, str] = {day: f"{day} : " for day in REGIME_DAYS}

PLANNING_JOURS: tuple[PlanningJourType, ...] = (
    "Dimanche",
    "Lundi",
    "Mardi",
    "Mercredi",
    "Jeudi",
    "Vendredi",
    "Samedi",
)
PLANNING_MOMENTS: tuple[PlanningMomentType, ...] = ("Midi", "Soir")


def ordered_week_days(premier_jour: str) -> tuple[PlanningJourType, ...]:
    """Rotation Lundi→Dimanche commençant par le jour choisi."""
    if premier_jour not in JOURS_ORDRE_ABSOLU:
        premier_jour = PREMIER_JOUR_DEFAUT
    idx = JOURS_ORDRE_ABSOLU.index(premier_jour)  # type: ignore[arg-type]
    return JOURS_ORDRE_ABSOLU[idx:] + JOURS_ORDRE_ABSOLU[:idx]


def ordered_meal_slots(premier_jour: str) -> tuple[str, ...]:
    """Créneaux midi/soir dans l'ordre de la semaine utilisateur."""
    return tuple(
        f"{day} {moment.lower()}"
        for day in ordered_week_days(premier_jour)
        for moment in PLANNING_MOMENTS
    )


def ordered_regime_days(premier_jour: str) -> tuple[PlanningJourType, ...]:
    return ordered_week_days(premier_jour)


class PlanningRepasItem(BaseModel):
    """Créneau repas — data pure renvoyée par l'IA (zéro HTML)."""

    jour: PlanningJourType
    moment: PlanningMomentType
    plat: str = Field(..., min_length=1)
    batch_cooking_dimanche: str = Field(
        ...,
        min_length=1,
        description="Préparations à faire en avance le dimanche",
    )
    action_minute: str = Field(
        ...,
        min_length=1,
        description="Actions rapides de dernière minute le jour J",
    )


class CourseItem(BaseModel):
    """Besoin culinaire hebdomadaire — paquets calculés côté code (règle de trois)."""

    mot_cle: str = Field(..., min_length=1)
    libelle: str = Field(..., min_length=1)
    rayon: RayonType
    quantite_recette: float = Field(..., ge=0.01)
    unite_recette: UniteMesureType


def format_besoin(course: CourseItem) -> str:
    qty = course.quantite_recette
    label = str(int(qty)) if qty == int(qty) else str(qty)
    if course.unite_recette == "u":
        return label
    return f"{label} {course.unite_recette}"


def format_article_besoin(course: CourseItem) -> str:
    return f"{course.mot_cle} (Besoin : {format_besoin(course)})"


def format_article_display(course: CourseItem) -> str:
    """Libellé épuré pour l'UI (sans quantité dupliquée)."""
    return course.libelle.strip() or course.mot_cle.strip()


def platform_id_from_label(label: str) -> DrivePlatformId:
    for platform_id, cfg in DRIVE_PLATFORMS.items():
        if cfg["label"] == label:
            return platform_id
    return DEFAULT_DRIVE_PLATFORM


def _harmoniser_besoin(
    quantite: float, unite_recette: UniteMesureType, unite_paquet: UniteMesureType
) -> float:
    """Convertit le besoin recette dans l'échelle du conditionnement magasin."""
    if unite_recette == unite_paquet:
        return quantite
    if unite_recette == "kg" and unite_paquet == "g":
        return quantite * 1000
    if unite_recette == "g" and unite_paquet == "kg":
        return quantite / 1000
    if unite_recette == "L" and unite_paquet == "ml":
        return quantite * 1000
    if unite_recette == "ml" and unite_paquet == "L":
        return quantite / 1000
    return quantite


def determiner_nb_clics(
    course: CourseItem,
    mapping: dict[str, Any] | None,
) -> int:
    """Règle de trois : besoin recette → nombre de paquets à cliquer sur Leclerc."""
    mapping = mapping or {}
    unite_paquet = _extract_unite_paquet(mapping, fallback=course.unite_recette)
    contenance = _extract_contenance_paquet(mapping, fallback=0.0)

    if contenance <= 0:
        return 0

    if unite_paquet == "u":
        return max(1, math.ceil(course.quantite_recette))

    besoin = _harmoniser_besoin(course.quantite_recette, course.unite_recette, unite_paquet)
    if unite_recette_incompatible(course.unite_recette, unite_paquet):
        return 0

    return max(1, math.ceil(besoin / contenance))


def unite_recette_incompatible(unite_recette: UniteMesureType, unite_paquet: UniteMesureType) -> bool:
    """True si les familles d'unités ne sont pas convertibles."""
    solids = {"g", "kg"}
    liquids = {"ml", "L"}
    if unite_recette in solids and unite_paquet in liquids:
        return True
    if unite_recette in liquids and unite_paquet in solids:
        return True
    if unite_recette == "u" or unite_paquet == "u":
        return unite_recette != unite_paquet
    pairs = {("g", "kg"), ("kg", "g"), ("ml", "L"), ("L", "ml")}
    return unite_recette != unite_paquet and (unite_recette, unite_paquet) not in pairs


def _extract_contenance_paquet(mapping: dict[str, Any], *, fallback: float = 0.0) -> float:
    if "contenance_paquet" in mapping:
        return float(mapping["contenance_paquet"])
    if "quantite_paquet" in mapping:
        return float(mapping["quantite_paquet"])
    return fallback


def _extract_unite_paquet(
    mapping: dict[str, Any], *, fallback: UniteMesureType = "u"
) -> UniteMesureType:
    raw = mapping.get("unite_paquet")
    if raw in UNITE_MESURE_OPTIONS:
        return raw
    return fallback


class DriveMenuAnalysisResult(BaseModel):
    planning_repas: list[PlanningRepasItem] = Field(default_factory=list)
    planning_regime: list[PlanningRepasItem] = Field(default_factory=list)
    liste_courses: list[CourseItem] = Field(..., min_length=1)


def planning_repas_sort_key(
    item: PlanningRepasItem,
    *,
    premier_jour: str = PREMIER_JOUR_DEFAUT,
) -> tuple[int, int]:
    moment_idx = 0 if item.moment == "Midi" else 1
    week_order = ordered_week_days(premier_jour)
    try:
        jour_idx = week_order.index(item.jour)
    except ValueError:
        jour_idx = 99
    return jour_idx, moment_idx


def sort_planning_repas(
    items: list[PlanningRepasItem],
    *,
    premier_jour: str = PREMIER_JOUR_DEFAUT,
) -> list[PlanningRepasItem]:
    return sorted(items, key=lambda i: planning_repas_sort_key(i, premier_jour=premier_jour))


def escape_html(text: str) -> str:
    return html_module.escape(text or "", quote=True)


class DriveShoppingItem(CourseItem):
    """Article sélectionné pour le robot — URL + paquets calculés."""

    product_url: str | None = None
    nb_paquets: int = Field(..., ge=0)


DriveSaisieMode = Literal["manual", "consignes"]


@dataclass
class DriveMenuInput:
    plats: dict[str, str] = field(default_factory=dict)
    regime_plats: dict[str, str] = field(default_factory=dict)
    extras: str = ""
    nb_convives_enfants: int = 4
    nb_convives_regime: int = 4
    semaine_reference: date = field(default_factory=compute_menu_week_sunday)
    premier_jour_semaine: PlanningJourType = PREMIER_JOUR_DEFAUT
    enfants_consignes: str = ""
    enfants_creneaux_cibles: list[str] = field(default_factory=list)
    regime_consignes: str = ""
    regime_creneaux_cibles: list[str] = field(default_factory=list)


def _strip_prefixed_line(raw: str, prefix: str) -> str | None:
    value = raw.replace(prefix, "", 1).strip() if raw.startswith(prefix) else raw.strip()
    if not value:
        return None
    prefix_body = prefix.strip().rstrip(":")
    if value == prefix_body:
        return None
    return value


def parse_prefixed_textarea(
    text: str,
    keys: tuple[str, ...],
    prefixes: dict[str, str],
) -> dict[str, str]:
    """Découpe un textarea ligne par ligne en dict clé → ligne brute (ordre par index)."""
    lines = (text or "").splitlines()
    return {key: lines[i] if i < len(lines) else prefixes[key] for i, key in enumerate(keys)}


def parse_prefixed_textarea_by_prefix(
    text: str,
    keys: tuple[str, ...],
    prefixes: dict[str, str],
) -> dict[str, str]:
    """Associe chaque clé à sa ligne via le préfixe (indépendant de l'ordre des lignes)."""
    result = {key: prefixes[key] for key in keys}
    prefix_only = {key: prefixes[key].strip().rstrip(":") for key in keys}
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for key in keys:
            prefix = prefixes[key]
            if stripped.startswith(prefix) or stripped == prefix_only[key]:
                result[key] = line
                break
    return result


def format_prefixed_textarea(values: dict[str, str], keys: tuple[str, ...]) -> str:
    return "\n".join(values[key] for key in keys)


def _slots_from_keys(keys: list[str], *, valid: tuple[str, ...]) -> list[str]:
    valid_set = set(valid)
    return [key for key in keys if key in valid_set]


def migrate_regime_creneaux_cibles(
    raw: list[str] | None,
    *,
    premier_jour: str = PREMIER_JOUR_DEFAUT,
) -> list[str]:
    """Migration : anciens jours (« Lundi ») → créneaux midi+soir."""
    if not raw:
        return []
    meal_slots = set(ordered_meal_slots(premier_jour))
    migrated: list[str] = []
    for key in raw:
        if key in meal_slots:
            migrated.append(key)
            continue
        if key in REGIME_DAYS or key in JOURS_ORDRE_ABSOLU:
            for moment in PLANNING_MOMENTS:
                slot = f"{key} {moment.lower()}"
                if slot in meal_slots:
                    migrated.append(slot)
    return _slots_from_keys(migrated, valid=tuple(meal_slots))


def build_drive_menu_input(
    meal_values: dict[str, str],
    regime_values: dict[str, str],
    extras: str,
    nb_convives_enfants: int,
    nb_convives_regime: int,
    *,
    premier_jour_semaine: str = PREMIER_JOUR_DEFAUT,
    enfants_consignes: str = "",
    enfants_creneaux_cibles: list[str] | None = None,
    regime_consignes: str = "",
    regime_creneaux_cibles: list[str] | None = None,
) -> DriveMenuInput:
    pj = premier_jour_semaine if premier_jour_semaine in JOURS_ORDRE_ABSOLU else PREMIER_JOUR_DEFAUT
    meal_slots = ordered_meal_slots(pj)
    creneaux_enfants = _slots_from_keys(list(enfants_creneaux_cibles or []), valid=meal_slots)
    creneaux_regime = migrate_regime_creneaux_cibles(
        list(regime_creneaux_cibles or []), premier_jour=pj
    )
    checked_enfants = set(creneaux_enfants) if creneaux_enfants else set(meal_slots)
    checked_regime = set(creneaux_regime) if creneaux_regime else set()

    plats = {
        slot: cleaned
        for slot in meal_slots
        if slot in checked_enfants
        and slot in meal_values
        and (cleaned := _strip_prefixed_line(meal_values[slot], MEAL_PREFIXES[slot]))
    }
    regime_plats = {
        slot: cleaned
        for slot in meal_slots
        if slot in checked_regime
        and slot in regime_values
        and (cleaned := _strip_prefixed_line(regime_values[slot], MEAL_PREFIXES[slot]))
    }
    return DriveMenuInput(
        plats=plats,
        regime_plats=regime_plats,
        extras=extras.strip(),
        nb_convives_enfants=max(1, int(nb_convives_enfants)),
        nb_convives_regime=max(1, int(nb_convives_regime)),
        semaine_reference=compute_menu_week_sunday(),
        premier_jour_semaine=pj,  # type: ignore[arg-type]
        enfants_consignes=(enfants_consignes or "").strip(),
        enfants_creneaux_cibles=creneaux_enfants,
        regime_consignes=(regime_consignes or "").strip(),
        regime_creneaux_cibles=creneaux_regime,
    )


def has_enfants_consignes(payload: DriveMenuInput) -> bool:
    return bool(payload.enfants_consignes) and bool(payload.enfants_creneaux_cibles)


def has_regime_consignes(payload: DriveMenuInput) -> bool:
    return bool(payload.regime_consignes) and bool(payload.regime_creneaux_cibles)


def has_regime_content(payload: DriveMenuInput) -> bool:
    return bool(payload.regime_plats) or has_regime_consignes(payload)


def resolve_allowed_meal_slots(payload: DriveMenuInput) -> set[tuple[str, str]] | None:
    """Créneaux autorisés : saisie manuelle + cibles consignes non couvertes manuellement."""
    allowed: set[tuple[str, str]] = set()
    manual_slots = set(payload.plats.keys())

    for slot in payload.plats:
        try:
            allowed.add(parse_meal_slot(slot))
        except ValueError:
            continue

    if has_enfants_consignes(payload):
        for slot in payload.enfants_creneaux_cibles:
            if slot in manual_slots:
                continue
            try:
                allowed.add(parse_meal_slot(slot))
            except ValueError:
                continue

    return allowed or None


def resolve_allowed_regime_slots(payload: DriveMenuInput) -> set[tuple[str, str]] | None:
    """Créneaux hôte régime : saisie manuelle + cibles consignes non couvertes manuellement."""
    allowed: set[tuple[str, str]] = set()
    manual_slots = set(payload.regime_plats.keys())

    for slot in payload.regime_plats:
        try:
            allowed.add(parse_meal_slot(slot))
        except ValueError:
            continue

    if has_regime_consignes(payload):
        for slot in payload.regime_creneaux_cibles:
            if slot in manual_slots:
                continue
            try:
                allowed.add(parse_meal_slot(slot))
            except ValueError:
                continue

    return allowed or None


def drive_menu_input_has_generatable_content(payload: DriveMenuInput) -> bool:
    if payload.extras.strip():
        return True
    if payload.plats:
        return True
    if has_enfants_consignes(payload):
        return True
    if payload.regime_plats:
        return True
    if has_regime_consignes(payload):
        return True
    return False


def mirror_planning_to_meals_text(
    result: DriveMenuAnalysisResult,
    *,
    premier_jour: str,
    existing_values: dict[str, str],
) -> str:
    """Réinjecte les plats générés dans le template préfixé (miroir post-génération)."""
    values = dict(existing_values)
    for item in result.planning_repas:
        slot = f"{item.jour} {item.moment.lower()}"
        if slot in MEAL_PREFIXES:
            values[slot] = f"{MEAL_PREFIXES[slot]}{item.plat}"
    return format_prefixed_textarea(values, ordered_meal_slots(premier_jour))


def mirror_planning_to_regime_text(
    result: DriveMenuAnalysisResult,
    *,
    premier_jour: str,
    existing_values: dict[str, str],
) -> str:
    """Réinjecte les plats hôte régime générés dans le template préfixé."""
    values = dict(existing_values)
    for item in result.planning_regime:
        slot = f"{item.jour} {item.moment.lower()}"
        if slot in MEAL_PREFIXES:
            values[slot] = f"{MEAL_PREFIXES[slot]}{item.plat}"
    return format_prefixed_textarea(values, ordered_meal_slots(premier_jour))


def default_meal_textarea_value(premier_jour: str = PREMIER_JOUR_DEFAUT) -> str:
    return "\n".join(MEAL_PREFIXES[slot] for slot in ordered_meal_slots(premier_jour))


def default_regime_textarea_value(premier_jour: str = PREMIER_JOUR_DEFAUT) -> str:
    return default_meal_textarea_value(premier_jour)
