"""Tests normalisation tags."""

from app.utils.tags import normalize_tag, normalize_tags


def test_normalize_tag_strips_accents():
    assert normalize_tag("répétition") == "repetition"


def test_normalize_tag_removes_special_chars():
    assert normalize_tag("re´pétition") == "repetition"


def test_normalize_tags_splits_phrases():
    assert normalize_tags("re´pétition de danse, hip-hop") == [
        "repetition",
        "danse",
        "hiphop",
    ]


def test_normalize_tags_max_five():
    assert len(normalize_tags(["a", "b", "c", "d", "e", "f"])) == 5
