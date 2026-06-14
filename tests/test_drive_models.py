"""Tests modèles Menu & Drive."""

from datetime import date

import pytest

from app.models.drive import (
    MEAL_PREFIXES,
    MEAL_SLOTS,
    CourseItem,
    DriveMenuAnalysisResult,
    PlanningRepasItem,
    build_drive_menu_input,
    drive_menu_input_has_generatable_content,
    migrate_regime_creneaux_cibles,
    mirror_planning_to_regime_text,
    ordered_meal_slots,
    ordered_week_days,
    parse_meal_slot,
    resolve_allowed_regime_slots,
    sort_planning_repas,
)
from app.utils.dates import compute_menu_week_sunday


def test_compute_menu_week_sunday_on_sunday():
    assert compute_menu_week_sunday(date(2026, 5, 31)) == date(2026, 5, 31)


def test_compute_menu_week_sunday_from_monday():
    assert compute_menu_week_sunday(date(2026, 6, 1)) == date(2026, 6, 7)


def test_compute_menu_week_sunday_from_saturday():
    assert compute_menu_week_sunday(date(2026, 6, 6)) == date(2026, 6, 7)


def test_parse_prefixed_textarea_meals():
    from app.models.drive import parse_prefixed_textarea

    text = "Dimanche midi : pâtes\nLundi midi : "
    values = parse_prefixed_textarea(text, MEAL_SLOTS, MEAL_PREFIXES)
    assert values["Dimanche midi"] == "Dimanche midi : pâtes"
    assert values["Lundi midi"] == "Lundi midi : "


def test_parse_meal_slot():
    assert parse_meal_slot("Mardi soir") == ("Mardi", "Soir")
    assert parse_meal_slot("Dimanche midi") == ("Dimanche", "Midi")


def test_parse_meal_slot_invalid():
    with pytest.raises(ValueError):
        parse_meal_slot("Mardi matin")


def test_build_drive_menu_input_strips_empty_prefix():
    payload = build_drive_menu_input(
        {"Dimanche midi": "Dimanche midi : "},
        {"Lundi midi": "Lundi midi : "},
        "",
        4,
        2,
        enfants_creneaux_cibles=["Dimanche midi"],
        regime_creneaux_cibles=["Lundi midi"],
    )
    assert payload.plats == {}
    assert payload.regime_plats == {}
    assert payload.nb_convives_enfants == 4
    assert payload.nb_convives_regime == 2


def test_build_drive_menu_input_keeps_filled_lines():
    payload = build_drive_menu_input(
        {"Dimanche midi": "Dimanche midi : pâtes"},
        {"Lundi midi": "Lundi midi : sans lactose"},
        "essuie-tout",
        4,
        4,
        enfants_creneaux_cibles=["Dimanche midi"],
        regime_creneaux_cibles=["Lundi midi"],
    )
    assert payload.plats["Dimanche midi"] == "pâtes"
    assert payload.regime_plats["Lundi midi"] == "sans lactose"
    assert payload.extras == "essuie-tout"


def test_build_drive_menu_input_strips_trailing_spaces():
    payload = build_drive_menu_input(
        {"Lundi midi": "Lundi midi :   quiche  "},
        {},
        "  ",
        0,
        3,
        enfants_creneaux_cibles=["Lundi midi"],
    )
    assert payload.plats["Lundi midi"] == "quiche"
    assert payload.nb_convives_enfants == 1
    assert payload.nb_convives_regime == 3


def test_course_item_rejects_invalid_rayon():
    with pytest.raises(Exception):
        CourseItem(
            mot_cle="test",
            libelle="test",
            rayon="Boulangerie",
            quantite_recette=1,
            unite_recette="u",
        )


def test_ordered_week_days_from_mercredi():
    assert ordered_week_days("Mercredi") == (
        "Mercredi",
        "Jeudi",
        "Vendredi",
        "Samedi",
        "Dimanche",
        "Lundi",
        "Mardi",
    )


def test_ordered_meal_slots_starts_with_premier_jour():
    slots = ordered_meal_slots("Vendredi")
    assert slots[0] == "Vendredi midi"
    assert slots[-1] == "Jeudi soir"


def test_sort_planning_repas_respects_premier_jour():
    items = [
        PlanningRepasItem(
            jour="Lundi",
            moment="Midi",
            plat="A",
            batch_cooking_dimanche="x",
            action_minute="y",
        ),
        PlanningRepasItem(
            jour="Mercredi",
            moment="Midi",
            plat="B",
            batch_cooking_dimanche="x",
            action_minute="y",
        ),
    ]
    sorted_default = sort_planning_repas(items)
    assert [p.plat for p in sorted_default] == ["A", "B"]
    sorted_mercredi = sort_planning_repas(items, premier_jour="Mercredi")
    assert [p.plat for p in sorted_mercredi] == ["B", "A"]


def test_build_drive_menu_input_premier_jour():
    payload = build_drive_menu_input(
        {"Mercredi midi": "Mercredi midi : tarte"},
        {},
        "",
        4,
        4,
        premier_jour_semaine="Mercredi",
        enfants_creneaux_cibles=["Mercredi midi"],
    )
    assert payload.premier_jour_semaine == "Mercredi"
    assert payload.plats["Mercredi midi"] == "tarte"


def test_build_drive_menu_input_consignes():
    payload = build_drive_menu_input(
        {},
        {},
        "",
        4,
        4,
        enfants_consignes="pas de lait",
        enfants_creneaux_cibles=["Lundi midi", "Invalid slot"],
        regime_consignes="sans gluten",
        regime_creneaux_cibles=["Lundi", "Dimanche midi"],
    )
    assert payload.enfants_consignes == "pas de lait"
    assert payload.enfants_creneaux_cibles == ["Lundi midi"]
    assert payload.regime_consignes == "sans gluten"
    assert "Lundi midi" in payload.regime_creneaux_cibles
    assert "Lundi soir" in payload.regime_creneaux_cibles
    assert "Dimanche midi" in payload.regime_creneaux_cibles


def test_migrate_regime_creneaux_cibles_from_days():
    migrated = migrate_regime_creneaux_cibles(["Lundi", "Mardi"])
    assert "Lundi midi" in migrated
    assert "Lundi soir" in migrated
    assert "Mardi midi" in migrated


def test_resolve_allowed_meal_slots_manual_and_consignes():
    from app.models.drive import DriveMenuInput, resolve_allowed_meal_slots

    payload = DriveMenuInput(
        plats={"Lundi midi": "quiche"},
        enfants_consignes="léger",
        enfants_creneaux_cibles=["Lundi midi", "Mardi soir"],
    )
    allowed = resolve_allowed_meal_slots(payload)
    assert allowed == {("Lundi", "Midi"), ("Mardi", "Soir")}


def test_resolve_allowed_regime_slots_manual_and_consignes():
    from app.models.drive import DriveMenuInput

    payload = DriveMenuInput(
        regime_plats={"Lundi midi": "salade"},
        regime_consignes="anti-constipation",
        regime_creneaux_cibles=["Lundi midi", "Mardi soir"],
    )
    allowed = resolve_allowed_regime_slots(payload)
    assert allowed == {("Lundi", "Midi"), ("Mardi", "Soir")}


def test_drive_menu_input_has_generatable_content():
    from app.models.drive import DriveMenuInput

    assert not drive_menu_input_has_generatable_content(DriveMenuInput())
    assert drive_menu_input_has_generatable_content(DriveMenuInput(extras="essuie-tout"))
    assert drive_menu_input_has_generatable_content(
        DriveMenuInput(
            enfants_consignes="enfant",
            enfants_creneaux_cibles=["Lundi midi"],
        )
    )
    assert drive_menu_input_has_generatable_content(
        DriveMenuInput(
            regime_consignes="sans gluten",
            regime_creneaux_cibles=["Lundi midi"],
        )
    )


def test_mirror_planning_to_regime_text():
    result = DriveMenuAnalysisResult(
        planning_repas=[],
        planning_regime=[
            PlanningRepasItem(
                jour="Mardi",
                moment="Soir",
                plat="Salade verte, haricots verts",
                batch_cooking_dimanche="Cuire haricots",
                action_minute="Assembler",
            )
        ],
        liste_courses=[
            CourseItem(
                mot_cle="haricots",
                libelle="Haricots verts",
                rayon="Fruits & Légumes",
                quantite_recette=400,
                unite_recette="g",
            )
        ],
    )
    text = mirror_planning_to_regime_text(
        result,
        premier_jour="Lundi",
        existing_values={slot: MEAL_PREFIXES[slot] for slot in MEAL_SLOTS},
    )
    assert "Mardi soir : Salade verte, haricots verts" in text


def test_drive_menu_analysis_result_min_items():
    result = DriveMenuAnalysisResult(
        planning_repas=[
            PlanningRepasItem(
                jour="Dimanche",
                moment="Midi",
                plat="Pâtes",
                batch_cooking_dimanche="Cuire la sauce",
                action_minute="Réchauffer",
            )
        ],
        liste_courses=[
            CourseItem(
                mot_cle="lait",
                libelle="lait entier",
                rayon="Frais",
                quantite_recette=2,
                unite_recette="L",
            )
        ],
    )
    assert len(result.liste_courses) == 1
    assert len(result.planning_repas) == 1
