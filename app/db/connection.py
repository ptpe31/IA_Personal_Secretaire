"""Connexion SQLite et initialisation de la base Trankil-v2."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from app import config
from app.db.migrations import apply_schema_migrations

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_PRODUCTION_DB_PATH = Path.home() / "Trankil-v2" / "database.sqlite"


def _guard_production_db_in_tests() -> None:
    """Empêche pytest d'écrire dans ~/Trankil-v2 si l'isolation échoue."""
    if os.environ.get("TRANKIL_TEST_MODE") != "1":
        return
    try:
        target = Path(config.DB_PATH).resolve()
        production = _PRODUCTION_DB_PATH.resolve()
    except OSError:
        target = Path(config.DB_PATH)
        production = _PRODUCTION_DB_PATH
    if target == production:
        raise RuntimeError(
            "Refus d'écrire dans ~/Trankil-v2/database.sqlite pendant les tests. "
            "Vérifiez tests/conftest.py (isolation SQLite)."
        )


def get_connection() -> sqlite3.Connection:
    """Ouvre une connexion SQLite vers ~/Trankil-v2/database.sqlite."""
    _guard_production_db_in_tests()
    config.ensure_directories()
    conn = sqlite3.connect(config.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    apply_schema_migrations(conn)
    return conn


def _read_schema() -> str:
    if not _SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"Schéma introuvable : {_SCHEMA_PATH}")
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def run_migrations(conn: sqlite3.Connection | None = None) -> None:
    """Applique les migrations incrémentales (bases existantes incluses)."""
    own_conn = conn is None
    if own_conn:
        config.ensure_directories()
        conn = sqlite3.connect(config.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
    try:
        apply_schema_migrations(conn)
    finally:
        if own_conn:
            conn.close()


def init_db(*, force: bool = False) -> None:
    """
    Initialise la base SQLite en exécutant schema.sql.

    Si force=False (défaut), n'exécute le schéma que si database.sqlite
    n'existe pas encore. Si force=True, ré-applique le schéma (idempotent).
    Les migrations incrémentales sont toujours appliquées.
    """
    _guard_production_db_in_tests()
    config.ensure_directories()

    db_exists = config.DB_PATH.is_file()
    if not db_exists or force:
        schema_sql = _read_schema()
        conn = sqlite3.connect(config.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.executescript(schema_sql)
            conn.commit()
        finally:
            conn.close()

    run_migrations()
    logger.info("Base SQLite prête — migrations vérifiées (%s).", config.DB_PATH)


def get_setting(key: str, default: str | None = None) -> str | None:
    """Lit une valeur dans la table settings."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        return str(row["value"])
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    """Écrit ou met à jour un paramètre."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return conn.execute(query, params).fetchone()
    finally:
        conn.close()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return list(conn.execute(query, params).fetchall())
    finally:
        conn.close()
