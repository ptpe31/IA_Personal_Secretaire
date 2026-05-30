"""Migrations incrémentales et backfill des données."""

from __future__ import annotations

import logging
import sqlite3

from app.utils.suggestion_infer import infer_rehearsal_suggestion, infer_spectacle_suggestion

logger = logging.getLogger(__name__)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _add_column_if_missing(
    conn: sqlite3.Connection,
    *,
    table: str,
    column: str,
    definition: str,
) -> None:
    if _column_exists(conn, table, column):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()
    logger.info("Migration SQLite : colonne %s.%s ajoutée.", table, column)


def backfill_task_suggestions(conn: sqlite3.Connection) -> None:
    """Remplit suggestion pour les tâches existantes créées avant la fonctionnalité."""
    if not _column_exists(conn, "tasks", "suggestion"):
        return

    rows = conn.execute(
        """
        SELECT id, title, justification_proof, raw_summary, suggestion
        FROM tasks
        WHERE suggestion IS NULL OR TRIM(suggestion) = ''
        """
    ).fetchall()
    if not rows:
        return

    updated = 0
    for row in rows:
        title = str(row["title"] or "")
        blob = " ".join(
            part
            for part in (title, row["justification_proof"], row["raw_summary"])
            if part and str(part).strip()
        )
        if not blob.strip():
            continue

        title_lower = title.lower()
        suggestion = None
        if "spectacle" in title_lower:
            suggestion = infer_spectacle_suggestion(blob)
        elif "répétition" in title_lower or "repetition" in title_lower:
            suggestion = infer_rehearsal_suggestion(blob)
        else:
            suggestion = infer_spectacle_suggestion(blob) or infer_rehearsal_suggestion(blob)

        if suggestion:
            conn.execute(
                "UPDATE tasks SET suggestion = ? WHERE id = ?",
                (suggestion, row["id"]),
            )
            updated += 1

    if updated:
        conn.commit()
        logger.info("Backfill suggestion : %s tâche(s) mise(s) à jour.", updated)


def apply_schema_migrations(conn: sqlite3.Connection) -> None:
    """Applique les migrations sur une base existante."""
    if not _table_exists(conn, "tasks"):
        return

    _add_column_if_missing(
        conn,
        table="tasks",
        column="justification_proof",
        definition="TEXT",
    )
    _add_column_if_missing(
        conn,
        table="tasks",
        column="suggestion",
        definition="TEXT",
    )
    _add_column_if_missing(
        conn,
        table="tasks",
        column="recurrence_pattern",
        definition="TEXT",
    )
    _add_column_if_missing(
        conn,
        table="tasks",
        column="parent_task_id",
        definition="INTEGER REFERENCES tasks(id) ON DELETE SET NULL",
    )
    backfill_task_suggestions(conn)

    _ensure_email_reminders_log(conn)

    if _table_exists(conn, "tasks"):
        _add_column_if_missing(conn, table="tasks", column="frequence", definition="TEXT")
        _add_column_if_missing(
            conn, table="tasks", column="date_reference", definition="DATE"
        )
        _add_column_if_missing(conn, table="tasks", column="source_url", definition="TEXT")

    if _table_exists(conn, "settings"):
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('autopilot_enabled', 'true')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('gemini_model', 'gemini-2.5-flash')"
        )
        conn.execute(
            """
            UPDATE settings SET value = 'gemini-2.5-flash'
            WHERE key = 'gemini_model'
              AND value IN (
                  'gemini-1.5-flash',
                  'gemini-1.5-pro',
                  'gemini-2.0-flash',
                  'gemini-2.0-flash-lite'
              )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('gemini_api_key', '')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES "
            "('active_ia_provider', 'Gemini (Natif)')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('openrouter_api_key', '')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES "
            "('openrouter_model', 'qwen/qwen-2.5-vl-72b-instruct')"
        )
        for key, value in (
            ("email_reminder_enabled", "true"),
            ("smtp_server", "smtp.gmail.com"),
            ("smtp_port", "587"),
            ("sender_email", ""),
            ("recipient_email", ""),
            ("email_reminder_last_sent_date", ""),
        ):
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()


def _ensure_email_reminders_log(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "email_reminders_log"):
        return
    conn.execute(
        """
        CREATE TABLE email_reminders_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            reminder_date DATE NOT NULL,
            sent_at DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
            UNIQUE (task_id, reminder_date)
        )
        """
    )
    conn.commit()
    logger.info("Migration SQLite : table email_reminders_log créée.")
