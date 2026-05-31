"""Tests pipeline Menu & Drive."""

from app.services.drive_analysis_pipeline import finalize_drive_analysis, sanitize_html_quotes


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
    data = {
        "planning_html": "<!DOCTYPE html><html lang='fr'><body></body></html>",
        "liste_courses": [
            {"mot_cle": "oeufs", "rayon": "Frais", "quantite": 2},
            {"mot_cle": "oeufs", "rayon": "Frais", "quantite": 3},
        ],
    }
    result = finalize_drive_analysis(data)
    assert len(result.liste_courses) == 1
    assert result.liste_courses[0].quantite == 5


def test_finalize_drive_analysis_normalizes_rayon():
    data = {
        "planning_html": "<!DOCTYPE html><html lang='fr'><body></body></html>",
        "liste_courses": [
            {"mot_cle": "lait", "rayon": "frais", "quantite": 1},
        ],
    }
    result = finalize_drive_analysis(data)
    assert result.liste_courses[0].rayon == "Frais"
