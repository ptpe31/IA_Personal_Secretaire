"""Tests export PDF planning Menu & Drive."""

from app.models.drive import CourseItem, DriveMenuAnalysisResult, PlanningRepasItem
from app.services.drive_pdf_service import render_planning_html


def test_render_planning_html_contains_data_not_template_noise():
    result = DriveMenuAnalysisResult(
        planning_repas=[
            PlanningRepasItem(
                jour="Lundi",
                moment="Midi",
                plat="Colombo de poulet",
                batch_cooking_dimanche="Mariner les blancs",
                action_minute="Air Fryer 15 min",
            )
        ],
        liste_courses=[
            CourseItem(
                mot_cle="poulet",
                libelle="Poulet",
                rayon="Frais",
                quantite_recette=1,
                unite_recette="kg",
            )
        ],
    )
    html = render_planning_html(
        result,
        semaine_label="07/06/2026",
        nb_convives_enfants=4,
        nb_convives_regime=2,
    )
    assert "Colombo de poulet" in html
    assert "Mariner les blancs" in html
    assert "Air Fryer 15 min" in html
    assert "Semaine du 07/06/2026" in html
    assert "Convives enfants : 4" in html
    assert "Plat hôte régime" in html
    assert "#166534" in html
    assert "DOCTYPE html" in html


def test_render_planning_html_includes_regime_column():
    result = DriveMenuAnalysisResult(
        planning_repas=[
            PlanningRepasItem(
                jour="Mardi",
                moment="Soir",
                plat="Fajitas",
                batch_cooking_dimanche="Mariner",
                action_minute="Assembler",
            )
        ],
        planning_regime=[
            PlanningRepasItem(
                jour="Mardi",
                moment="Soir",
                plat="Salade verte, haricots verts",
                batch_cooking_dimanche="Cuire haricots",
                action_minute="Assembler salade",
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
    html = render_planning_html(result, semaine_label="07/06/2026")
    assert "Fajitas" in html
    assert "Salade verte, haricots verts" in html
    assert "Cuire haricots" in html

    result = DriveMenuAnalysisResult(
        planning_repas=[
            PlanningRepasItem(
                jour="Mardi",
                moment="Soir",
                plat='Plat "spécial" & <test>',
                batch_cooking_dimanche="Préparer",
                action_minute="Servir",
            )
        ],
        liste_courses=[
            CourseItem(
                mot_cle="test",
                libelle="Test",
                rayon="Frais",
                quantite_recette=1,
                unite_recette="u",
            )
        ],
    )
    html = render_planning_html(result, semaine_label="01/01/2026")
    assert "&lt;test&gt;" in html
    assert '"spécial"' not in html
