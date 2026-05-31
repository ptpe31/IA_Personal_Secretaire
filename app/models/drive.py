"""Modèles Menu & Drive — planning batch cooking + liste courses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.utils.dates import compute_menu_week_sunday

RayonType = Literal["Épicerie", "Frais", "Fruits & Légumes", "Bébé", "Entretien"]

RAYON_ORDER: tuple[RayonType, ...] = (
    "Épicerie",
    "Frais",
    "Fruits & Légumes",
    "Bébé",
    "Entretien",
)

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
REGIME_PREFIXES: dict[str, str] = {day: f"{day} : " for day in REGIME_DAYS}


class CourseItem(BaseModel):
    mot_cle: str = Field(..., min_length=1)
    rayon: RayonType
    quantite: int = Field(..., ge=1)


class DriveMenuAnalysisResult(BaseModel):
    planning_html: str = Field(..., min_length=1)
    liste_courses: list[CourseItem] = Field(..., min_length=1)


@dataclass
class DriveMenuInput:
    plats: dict[str, str] = field(default_factory=dict)
    regime: dict[str, str] = field(default_factory=dict)
    extras: str = ""
    nb_convives: int = 4
    semaine_reference: date = field(default_factory=compute_menu_week_sunday)


def _strip_prefixed_line(raw: str, prefix: str) -> str | None:
    value = raw.replace(prefix, "", 1).strip() if raw.startswith(prefix) else raw.strip()
    if not value:
        return None
    prefix_body = prefix.strip().rstrip(":")
    if value == prefix_body:
        return None
    return value


def build_drive_menu_input(
    meal_values: dict[str, str],
    regime_values: dict[str, str],
    extras: str,
    nb_convives: int,
) -> DriveMenuInput:
    plats = {
        slot: cleaned
        for slot in MEAL_SLOTS
        if slot in meal_values and (cleaned := _strip_prefixed_line(meal_values[slot], MEAL_PREFIXES[slot]))
    }
    regime = {
        day: cleaned
        for day in REGIME_DAYS
        if day in regime_values and (cleaned := _strip_prefixed_line(regime_values[day], REGIME_PREFIXES[day]))
    }
    convives = max(1, int(nb_convives))
    return DriveMenuInput(
        plats=plats,
        regime=regime,
        extras=extras.strip(),
        nb_convives=convives,
        semaine_reference=compute_menu_week_sunday(),
    )


def default_meal_input_values() -> dict[str, str]:
    return dict(MEAL_PREFIXES)


def default_regime_textarea_value() -> str:
    return "\n".join(REGIME_PREFIXES[day] for day in REGIME_DAYS)
