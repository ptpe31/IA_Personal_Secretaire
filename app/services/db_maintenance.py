"""Maintenance de la base SQLite Trankil-v2."""

from __future__ import annotations

import logging

from app.db.connection import get_connection

logger = logging.getLogger(__name__)

_DATA_TABLES = (
    "notifications_log",
    "task_tags",
    "tasks",
    "documents",
    "tags",
)


def get_application_data_counts() -> dict[str, int]:
    """Compte les enregistrements métier (hors settings)."""
    conn = get_connection()
    try:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _DATA_TABLES
        }
    finally:
        conn.close()


def purge_application_data() -> dict[str, int]:
    """
    Vide les données métier SQLite.

    Conserve la table settings (Autopilote, modèles IA, Calendar…).
    Ne supprime pas les fichiers GED ni le dossier .inbox sur disque.
    """
    conn = get_connection()
    try:
        before = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _DATA_TABLES
        }
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in _DATA_TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ({})".format(
            ", ".join(f"'{table}'" for table in _DATA_TABLES)
        ))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        logger.warning(
            "Base SQLite vidée — %s tâche(s), %s document(s) supprimé(s).",
            before["tasks"],
            before["documents"],
        )
        return before
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
