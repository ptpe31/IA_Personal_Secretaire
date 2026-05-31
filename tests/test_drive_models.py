"""Tests modèles Menu & Drive."""

from datetime import date

import pytest

from app.models.drive import (
    MEAL_PREFIXES,
    REGIME_PREFIXES,
    CourseItem,
    DriveMenuAnalysisResult,
    build_drive_menu_input,
)
from app.utils.dates import compute_menu_week_sunday


def test_compute_menu_week_sunday_on_sunday():
    assert compute_menu_week_sunday(date(2026, 5, 31)) == date(2026, 5, 31)


def test_compute_menu_week_sunday_from_monday():
    assert compute_menu_week_sunday(date(2026, 6, 1)) == date(2026, 6, 7)


def test_compute_menu_week_sunday_from_saturday():
    assert compute_menu_week_sunday(date(2026, 6, 6)) == date(2026, 6, 7)


def test_build_drive_menu_input_strips_empty_prefix():
    payload = build_drive_menu_input(
        {"Dimanche midi": "Dimanche midi : "},
        {"Lundi": "Lundi : "},
        "",
        4,
    )
    assert payload.plats == {}
    assert payload.regime == {}
    assert payload.nb_convives == 4


def test_build_drive_menu_input_keeps_filled_lines():
    payload = build_drive_menu_input(
        {"Dimanche midi": "Dimanche midi : pâtes"},
        {"Lundi": "Lundi : sans lactose"},
        "essuie-tout",
        4,
    )
    assert payload.plats["Dimanche midi"] == "pâtes"
    assert payload.regime["Lundi"] == "sans lactose"
    assert payload.extras == "essuie-tout"


def test_build_drive_menu_input_strips_trailing_spaces():
    payload = build_drive_menu_input(
        {"Lundi midi": "Lundi midi :   quiche  "},
        {},
        "  ",
        0,
    )
    assert payload.plats["Lundi midi"] == "quiche"
    assert payload.nb_convives == 1


def test_course_item_rejects_invalid_rayon():
    with pytest.raises(Exception):
        CourseItem(mot_cle="test", rayon="Boulangerie", quantite=1)


def test_drive_menu_analysis_result_min_items():
    html = "<!DOCTYPE html><html lang='fr'><body><p>x</p></body></html>"
    result = DriveMenuAnalysisResult(
        planning_html=html,
        liste_courses=[CourseItem(mot_cle="lait", rayon="Frais", quantite=1)],
    )
    assert len(result.liste_courses) == 1
