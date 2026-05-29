"""Tests nommage GED."""

from datetime import date

from app.utils.slugify import build_ged_filename, slugify_title, unique_path


def test_slugify_title_ascii():
    assert slugify_title("Maintenance Expo SDK") == "Maintenance_Expo_SDK"


def test_slugify_strips_accents():
    assert slugify_title("Déclaration TVA — URSSAF") == "Declaration_TVA_URSSAF"


def test_build_ged_filename():
    result = build_ged_filename(date(2026, 5, 28), "Maintenance Expo SDK", ".png")
    assert result == "2026-05-28_Maintenance_Expo_SDK.png"


def test_unique_path_avoids_collision(tmp_path):
    first = tmp_path / "2026-05-28_Test.pdf"
    first.write_bytes(b"x")
    second = unique_path(tmp_path, "2026-05-28_Test.pdf")
    assert second.name == "2026-05-28_Test_2.pdf"
