"""Tests utilitaires URL Leclerc Drive."""

from app.services.drive_mapping_service import (
    ensure_plus_url,
    extract_product_id,
    is_leclerc_product_fiche,
    normalize_product_url,
)


def test_normalize_product_url_strips_plus_fragment():
    url = "https://fd4-courses.leclercdrive.fr/fiche-produits-123.aspx#plus"
    assert normalize_product_url(url) == (
        "https://fd4-courses.leclercdrive.fr/fiche-produits-123.aspx"
    )


def test_ensure_plus_url():
    base = "https://fd4-courses.leclercdrive.fr/fiche-produits-456.aspx"
    assert ensure_plus_url(base) == f"{base}#plus"
    assert ensure_plus_url(f"{base}#plus") == f"{base}#plus"


def test_extract_product_id_from_fiche():
    url = "https://fd4-courses.leclercdrive.fr/magasin/fiche-produits-789.aspx"
    assert extract_product_id(url) == "789"


def test_is_leclerc_product_fiche():
    fiche = (
        "https://fd4-courses.leclercdrive.fr/"
        "magasin-103101/fiche-produits-12345.aspx"
    )
    store = (
        "https://fd4-courses.leclercdrive.fr/"
        "magasin-103101-103101-Roques-sur-Garonne-Toulouse.aspx"
    )
    search = "https://fd4-courses.leclercdrive.fr/recherche.aspx?q=oeufs"
    assert is_leclerc_product_fiche(fiche) is True
    assert is_leclerc_product_fiche(store) is False
    assert is_leclerc_product_fiche(search) is False
