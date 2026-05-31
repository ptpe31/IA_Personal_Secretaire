"""Tests prompts Menu & Drive."""

from datetime import date

from app.models.drive import DriveMenuInput
from app.services.drive_prompt import build_drive_user_prompt


def test_build_drive_user_prompt_includes_date():
    payload = DriveMenuInput(
        plats={"Lundi midi": "quiche"},
        nb_convives=4,
        semaine_reference=date(2026, 6, 7),
    )
    prompt = build_drive_user_prompt(payload)
    assert "Semaine du 07/06/2026" in prompt
    assert "4 personnes" in prompt
    assert "Lundi midi : quiche" in prompt


def test_build_drive_user_prompt_empty_sections():
    payload = DriveMenuInput(semaine_reference=date(2026, 6, 7))
    prompt = build_drive_user_prompt(payload)
    assert "(aucun plat enfant saisi)" in prompt
    assert "(aucune contrainte régime saisie)" in prompt
    assert "(aucun extra)" in prompt
