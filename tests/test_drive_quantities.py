"""Tests calcul logistique Menu & Drive."""

import pytest

from app.models.drive import CourseItem, determiner_nb_clics, format_article_besoin, format_besoin


def _item(**kwargs) -> CourseItem:
    defaults = {
        "mot_cle": "test",
        "libelle": "test",
        "rayon": "Frais",
        "quantite_recette": 1.0,
        "unite_recette": "u",
    }
    defaults.update(kwargs)
    return CourseItem(**defaults)


def test_determiner_nb_clics_lait_3L_bouteille_1L():
    item = _item(mot_cle="lait entier", quantite_recette=3, unite_recette="L")
    mapping = {"contenance_paquet": 1.0, "unite_paquet": "L"}
    assert determiner_nb_clics(item, mapping) == 3


def test_determiner_nb_clics_pommes_1_2kg_filet_2_5kg():
    item = _item(mot_cle="pomme de terre", quantite_recette=1.2, unite_recette="kg")
    mapping = {"contenance_paquet": 2.5, "unite_paquet": "kg"}
    assert determiner_nb_clics(item, mapping) == 1


def test_determiner_nb_clics_essuie_tout_unites():
    item = _item(mot_cle="essuie-tout", quantite_recette=2, unite_recette="u")
    mapping = {"contenance_paquet": 1.0, "unite_paquet": "u"}
    assert determiner_nb_clics(item, mapping) == 2


def test_determiner_nb_clics_conversion_kg_vers_g():
    item = _item(quantite_recette=1.2, unite_recette="kg")
    mapping = {"contenance_paquet": 500, "unite_paquet": "g"}
    assert determiner_nb_clics(item, mapping) == 3


def test_determiner_nb_clics_conversion_L_vers_ml():
    item = _item(quantite_recette=2.5, unite_recette="L")
    mapping = {"contenance_paquet": 1000, "unite_paquet": "ml"}
    assert determiner_nb_clics(item, mapping) == 3


def test_determiner_nb_clics_sans_mapping_default_0():
    item = _item(quantite_recette=200, unite_recette="g")
    assert determiner_nb_clics(item, {}) == 0


def test_determiner_nb_clics_contenance_zero():
    item = _item(quantite_recette=100, unite_recette="g")
    mapping = {"contenance_paquet": 0, "unite_paquet": "g"}
    assert determiner_nb_clics(item, mapping) == 0


def test_format_besoin_and_article():
    item = _item(mot_cle="lait entier", quantite_recette=3, unite_recette="L")
    assert format_besoin(item) == "3 L"
    assert format_article_besoin(item) == "lait entier (Besoin : 3 L)"


def test_course_item_requires_libelle():
    with pytest.raises(Exception):
        CourseItem(mot_cle="x", rayon="Frais", quantite_recette=1, unite_recette="u")
