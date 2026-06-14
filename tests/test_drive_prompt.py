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
    assert "(aucun plat enfant saisi manuellement)" in prompt
    assert "(aucune contrainte régime saisie manuellement)" in prompt
    assert "(aucun extra)" in prompt
    assert "planning_repas" in prompt


def test_build_drive_user_prompt_enfants_consignes():
    payload = DriveMenuInput(
        enfants_consignes="repas enfant, pas de lait",
        enfants_creneaux_cibles=["Lundi midi", "Mardi soir"],
        semaine_reference=date(2026, 6, 7),
    )
    prompt = build_drive_user_prompt(payload)
    assert "CONSIGNES ENFANTS (IA)" in prompt
    assert "repas enfant, pas de lait" in prompt
    assert "CRÉNEAUX À GÉNÉRER (consignes IA)" in prompt
    assert "→ Lundi midi" in prompt
    assert "→ Mardi soir" in prompt


def test_build_drive_user_prompt_regime_consignes():
    payload = DriveMenuInput(
        regime_consignes="sans gluten",
        regime_jours_cibles=["Lundi", "Mercredi"],
        semaine_reference=date(2026, 6, 7),
    )
    prompt = build_drive_user_prompt(payload)
    assert "CONSIGNES RÉGIME (IA)" in prompt
    assert "sans gluten" in prompt
    assert "JOURS RÉGIME À GÉNÉRER" in prompt


def test_build_drive_system_prompt_consignes_mode():
    payload = DriveMenuInput(
        enfants_consignes="léger",
        enfants_creneaux_cibles=["Lundi midi"],
    )
    prompt = build_drive_system_prompt(payload)
    assert "Mode consignes IA" in prompt
    assert "invente un plat adapté" in prompt


def test_build_drive_system_prompt_manual_mode():
    prompt = build_drive_system_prompt(DriveMenuInput(plats={"Lundi midi": "quiche"}))
    assert "Mode saisie manuelle" in prompt
    assert "n'invente pas de repas" in prompt


def test_build_drive_user_prompt_chronologie():
    payload = DriveMenuInput(
        plats={"Mercredi midi": "tarte"},
        premier_jour_semaine="Mercredi",
        semaine_reference=date(2026, 6, 7),
    )
    prompt = build_drive_user_prompt(payload)
    assert "CHRONOLOGIE DE LA SEMAINE" in prompt
    assert "Premier jour de la semaine : Mercredi" in prompt
    assert "Mercredi → Jeudi → Vendredi" in prompt


def test_build_drive_user_prompt_single_slot_constraint():
    payload = DriveMenuInput(
        plats={"Mardi soir": "épinard haché"},
        semaine_reference=date(2026, 6, 7),
    )
    prompt = build_drive_user_prompt(payload)
    assert "Mardi soir : épinard haché" in prompt
    assert "1 créneau(x) autorisé(s) sur 14" in prompt
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
