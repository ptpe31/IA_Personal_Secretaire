"""Tests export PDF planning Menu & Drive."""

from app.models.drive import CourseItem, DriveMenuAnalysisResult, PlanningRepasItem, escape_html
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
        premier_jour_semaine="Mercredi",
    )
    assert "Colombo de poulet" in html
    assert "Mariner les blancs" in html
    assert "Air Fryer 15 min" in html
    assert "Semaine du 07/06/2026" in html
    assert "Convives enfants : 4" in html
    assert "Enfants" in html
    assert "Batch mercredi" in html
    assert "batch-premier-jour" in html
    assert "color: #ffffff" in html
    assert ">Lundi<" in html
    assert ">Midi<" in html
    assert ">Soir<" in html
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
    assert "Convives" in html
    assert ">Mardi<" in html

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


def test_render_planning_html_unifies_duplicate_batch_per_day():
    shared_batch = "Cuire et portionner les légumes"
    result = DriveMenuAnalysisResult(
        planning_repas=[
            PlanningRepasItem(
                jour="Mercredi",
                moment="Midi",
                plat="Purée",
                batch_cooking_dimanche=shared_batch,
                action_minute="Réchauffer",
            )
        ],
        planning_regime=[
            PlanningRepasItem(
                jour="Mercredi",
                moment="Midi",
                plat="Carottes vapeur",
                batch_cooking_dimanche=shared_batch,
                action_minute="Servir",
            )
        ],
        liste_courses=[
            CourseItem(
                mot_cle="carotte",
                libelle="Carottes",
                rayon="Fruits & Légumes",
                quantite_recette=500,
                unite_recette="g",
            )
        ],
    )
    html = render_planning_html(result, semaine_label="07/06/2026")
    assert html.count(escape_html(shared_batch)) == 1
