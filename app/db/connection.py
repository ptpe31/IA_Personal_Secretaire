"""Connexion SQLite et initialisation de la base Trankil-v2."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.config import DB_PATH, ensure_directories

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Ouvre une connexion SQLite vers ~/Trankil-v2/database.sqlite."""
    ensure_directories()
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _read_schema() -> str:
    if not _SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"Schéma introuvable : {_SCHEMA_PATH}")
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def init_db(*, force: bool = False) -> None:
    """
    Initialise la base SQLite en exécutant schema.sql.

    Si force=False (défaut), n'exécute le schéma que si database.sqlite
    n'existe pas encore. Si force=True, ré-applique le schéma (idempotent).
    """
    ensure_directories()

    db_exists = DB_PATH.is_file()
    if db_exists and not force:
        return

    schema_sql = _read_schema()
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


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
