"""Tests pipeline Menu & Drive."""

import pytest

from app.models.drive import PlanningRepasItem
from app.services.drive_analysis_pipeline import (
    filter_planning_to_input,
    finalize_drive_analysis,
    sanitize_html_quotes,
    strip_quantity_from_text,
)


def _sample_planning(**kwargs):
    defaults = {
        "jour": "Lundi",
        "moment": "Midi",
        "plat": "Quiche",
        "batch_cooking_dimanche": "Préparer la pâte",
        "action_minute": "Enfourner 25 min",
    }
    defaults.update(kwargs)
    return defaults


def _sample_data(**overrides):
    data = {
        "planning_repas": [_sample_planning()],
        "liste_courses": [
            {
                "mot_cle": "oeufs",
                "libelle": "oeufs",
                "rayon": "Frais",
                "quantite_recette": 6,
                "unite_recette": "u",
            }
        ],
    }
    data.update(overrides)
    return data


def test_sanitize_html_quotes_in_tags():
    assert sanitize_html_quotes('<table class="main">') == "<table class='main'>"


def test_sanitize_html_quotes_multiple_attrs():
    html = '<div class="a" id="b">'
    result = sanitize_html_quotes(html)
    assert '"' not in result.split(">")[0]


def test_sanitize_html_preserves_text_between_tags():
    html = '<p class="x">say "hello"</p>'
    result = sanitize_html_quotes(html)
    assert 'say "hello"' in result


def test_finalize_drive_analysis_dedupes_courses():
    data = _sample_data(
        liste_courses=[
            {
                "mot_cle": "oeufs",
                "libelle": "oeufs",
                "rayon": "Frais",
                "quantite_recette": 6,
                "unite_recette": "u",
            },
            {
                "mot_cle": "oeufs",
                "libelle": "oeufs",
                "rayon": "Frais",
                "quantite_recette": 6,
                "unite_recette": "u",
            },
        ]
    )
    result = finalize_drive_analysis(data)
    assert len(result.liste_courses) == 1
    assert result.liste_courses[0].quantite_recette == 12


def test_finalize_drive_analysis_legacy_fields():
    data = {
        "planning_repas": [_sample_planning(plat="Lait chaud")],
        "liste_courses": [
            {"mot_cle": "lait", "rayon": "Frais", "quantite": 2, "unite": "L"},
        ],
    }
    result = finalize_drive_analysis(data)
    assert result.liste_courses[0].quantite_recette == 2
    assert result.liste_courses[0].unite_recette == "L"
    assert result.liste_courses[0].libelle == "Lait"


def test_finalize_drive_analysis_normalizes_rayon():
    data = _sample_data(
        liste_courses=[
            {
                "mot_cle": "lait",
                "libelle": "lait entier",
                "rayon": "frais",
                "quantite_recette": 1,
                "unite_recette": "L",
            },
        ]
    )
    result = finalize_drive_analysis(data)
    assert result.liste_courses[0].rayon == "Frais"


def test_finalize_drive_analysis_sorts_planning_repas():
    data = _sample_data(
        planning_repas=[
            _sample_planning(jour="Mercredi", moment="Soir", plat="Soupe"),
            _sample_planning(jour="Lundi", moment="Midi", plat="Quiche"),
            _sample_planning(jour="Lundi", moment="Soir", plat="Salade"),
        ]
    )
    result = finalize_drive_analysis(data)
    assert [p.plat for p in result.planning_repas] == ["Quiche", "Salade", "Soupe"]


def test_finalize_drive_analysis_rejects_empty_planning():
    with pytest.raises(ValueError, match="planning_repas"):
        finalize_drive_analysis(_sample_data(planning_repas=[]))


def test_finalize_drive_analysis_filters_invented_slots():
    data = _sample_data(
        planning_repas=[
            _sample_planning(jour="Mardi", moment="Soir", plat="Épinards hachés"),
            _sample_planning(jour="Dimanche", moment="Midi", plat="Rôti de bœuf"),
            _sample_planning(jour="Lundi", moment="Midi", plat="Poulet rôti"),
        ]
    )
    result = finalize_drive_analysis(data, input_plats={"Mardi soir": "épinard haché"})
    assert len(result.planning_repas) == 1
    assert result.planning_repas[0].plat == "Épinards hachés"


def test_filter_planning_to_input_no_filter_without_input():
    items = [
        PlanningRepasItem(
            jour="Lundi",
            moment="Midi",
            plat="Quiche",
            batch_cooking_dimanche="—",
            action_minute="—",
        )
    ]
    assert filter_planning_to_input(items, None) == items


def test_strip_quantity_from_mot_cle_and_libelle():
    data = _sample_data(
        liste_courses=[
            {
                "mot_cle": "600 g épinards hachés",
                "libelle": "600 g épinards hachés surgelés",
                "rayon": "Frais",
                "quantite_recette": 600,
                "unite_recette": "g",
            },
        ]
    )
    result = finalize_drive_analysis(data)
    item = result.liste_courses[0]
    assert item.mot_cle == "épinards hachés"
    assert item.libelle == "Épinards hachés surgelés"
    assert "600 g" not in item.libelle


def test_truncate_mot_cle_and_libelle_to_three_words():
    data = _sample_data(
        liste_courses=[
            {
                "mot_cle": "pommes de terre chair fermes",
                "libelle": "pommes de terre chair fermes bio",
                "rayon": "Fruits & Légumes",
                "quantite_recette": 1,
                "unite_recette": "kg",
            },
        ]
    )
    result = finalize_drive_analysis(data)
    item = result.liste_courses[0]
    assert item.mot_cle == "pommes de terre"
    assert item.libelle == "Pommes de terre"
    assert len(item.mot_cle.split()) <= 3
    assert len(item.libelle.split()) <= 3


def test_strip_quantity_from_text_helper():
    assert strip_quantity_from_text("600 g épinards", quantite=600, unite="g") == "épinards"
    assert strip_quantity_from_text("3 L lait entier", quantite=3, unite="L") == "lait entier"
