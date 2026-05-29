"""Fixtures pytest — base SQLite isolée (ne pollue pas ~/Trankil-v2)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_trankil_data(monkeypatch, tmp_path):
    """Redirige données et SQLite vers un dossier temporaire par test."""
    root = tmp_path / "Trankil-v2"
    db_path = root / "database.sqlite"
    inbox = root / ".inbox"
    pro_ged = root / "Pro" / "GED"
    perso_ged = root / "Perso" / "GED"
    credentials = root / ".credentials" / "google_calendar"

    for directory in (inbox, pro_ged, perso_ged, credentials):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("app.config.ROOT_PATH", root)
    monkeypatch.setattr("app.config.DB_PATH", db_path)
    monkeypatch.setattr("app.config.INBOX_PATH", inbox)
    monkeypatch.setattr("app.config.PRO_GED_PATH", pro_ged)
    monkeypatch.setattr("app.config.PERSO_GED_PATH", perso_ged)
    monkeypatch.setattr("app.config.CREDENTIALS_PATH", credentials)
    monkeypatch.setattr("app.services.ged_service.ROOT_PATH", root)
    monkeypatch.setattr("app.services.archive_service.ROOT_PATH", root)

    from app.db.connection import init_db

    init_db(force=True)
