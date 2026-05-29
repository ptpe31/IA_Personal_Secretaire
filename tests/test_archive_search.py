"""Tests recherche archives GED."""

from app.services.archive_service import matches_search_query


def test_matches_empty_query():
    assert matches_search_query(
        query="",
        title="Facture EDF",
        raw_summary="Montant 120 euros",
        stored_path="Pro/GED/2026-05-20_Facture.pdf",
        original_filename="scan.pdf",
        tags=["Charges"],
    )


def test_matches_title():
    assert matches_search_query(
        query="expo",
        title="Mettre à jour Expo",
        raw_summary="",
        stored_path="Pro/GED/file.png",
        original_filename="file.png",
        tags=[],
    )


def test_matches_raw_summary():
    assert matches_search_query(
        query="maintenance",
        title="Tâche",
        raw_summary="Maintenance obligatoire du SDK",
        stored_path="x.pdf",
        original_filename="x.pdf",
        tags=[],
    )


def test_matches_tags():
    assert matches_search_query(
        query="urssaf",
        title="Déclaration",
        raw_summary="",
        stored_path="x.pdf",
        original_filename="x.pdf",
        tags=["Compta", "URSSAF"],
    )


def test_no_match():
    assert not matches_search_query(
        query="firebase",
        title="Mettre à jour Expo",
        raw_summary="Maintenance Expo",
        stored_path="Pro/GED/expo.png",
        original_filename="expo.png",
        tags=["Tech"],
    )
