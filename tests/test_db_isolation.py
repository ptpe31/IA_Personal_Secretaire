"""Vérifie que les tests n'écrivent jamais dans la base de production."""

import os
from pathlib import Path

import pytest

from app import config


def test_tests_never_target_production_database(monkeypatch, tmp_path):
    """Garde-fou : TRANKIL_TEST_MODE + chemin prod → RuntimeError."""
    os.environ["TRANKIL_TEST_MODE"] = "1"
    production = Path.home() / "Trankil-v2" / "database.sqlite"
    monkeypatch.setattr(config, "DB_PATH", production)

    from app.db.connection import get_connection

    with pytest.raises(RuntimeError, match="Refus d'écrire"):
        get_connection()
