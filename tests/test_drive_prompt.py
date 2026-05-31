"""Tests prompts Menu & Drive."""

from datetime import date

from app.models.drive import DriveMenuInput
from app.services.drive_prompt import build_drive_system_prompt, build_drive_user_prompt


def test_build_drive_user_prompt_includes_date():
    payload = DriveMenuInput(
        plats={"Lundi midi": "quiche"},
        nb_convives_enfants=3,
        nb_convives_regime=2,
        semaine_reference=date(2026, 6, 7),
    )
    prompt = build_drive_user_prompt(payload)
    assert "Semaine du 07/06/2026" in prompt
    assert "CONVIVES ENFANTS" in prompt
    assert "3 personnes" in prompt
    assert "CONVIVES RÉGIME" in prompt
    assert "2 personnes" in prompt
    assert "Lundi midi : quiche" in prompt


def test_build_drive_user_prompt_empty_sections():
    payload = DriveMenuInput(semaine_reference=date(2026, 6, 7))
    prompt = build_drive_user_prompt(payload)
    assert "(aucun plat enfant saisi)" in prompt
    assert "(aucune contrainte régime saisie)" in prompt
    assert "(aucun extra)" in prompt
    assert "planning_repas" in prompt


def test_build_drive_user_prompt_single_slot_constraint():
    payload = DriveMenuInput(
        plats={"Mardi soir": "épinard haché"},
        semaine_reference=date(2026, 6, 7),
    )
    prompt = build_drive_user_prompt(payload)
    assert "Mardi soir : épinard haché" in prompt
    assert "1 créneau(x) saisi(s) sur 14" in prompt
    assert "jour='Mardi', moment='Soir'" in prompt
    assert "Ne génère AUCUN autre repas" in prompt


def test_build_drive_system_prompt_only_saisi_creneaux():
    prompt = build_drive_system_prompt()
    assert "UNIQUEMENT un objet pour chaque créneau EXPLICITEMENT listé" in prompt
    assert "n'invente pas de repas" in prompt


def test_build_drive_system_prompt_requests_structured_planning():
    prompt = build_drive_system_prompt()
    assert "planning_repas" in prompt
    assert "planning_html" not in prompt
    assert "AUCUN code HTML" in prompt
