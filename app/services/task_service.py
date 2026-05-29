"""Service métier tâches, tags et validation Inbox."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from app.db.connection import get_connection
from app.models.task import TaskDTO
from app.services.ged_service import file_sha256, guess_mime_type, move_inbox_to_ged
from app.utils.dates import compute_db_status, compute_kanban_column, parse_optional_date

logger = logging.getLogger(__name__)


def parse_tags_input(raw: str) -> list[str]:
    """Parse tags séparés par virgules."""
    tags: list[str] = []
    for part in raw.split(","):
        cleaned = part.strip().lstrip("#")
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tags[:5]


def _upsert_tags(conn, tag_names: list[str]) -> list[int]:
    tag_ids: list[int] = []
    for name in tag_names:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        if row:
            tag_ids.append(int(row["id"]))
    return tag_ids


def _link_task_tags(conn, task_id: int, tag_ids: list[int]) -> None:
    conn.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    for tag_id in tag_ids:
        conn.execute(
            "INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)",
            (task_id, tag_id),
        )


def validate_inbox_document(
    inbox_path: Path,
    *,
    title: str,
    date_emission: date,
    date_event: date | None,
    deadline: date | None,
    category: str,
    tags: list[str],
    raw_summary: str,
) -> int:
    """
    Valide un document Inbox : GED + documents + tasks + tags.

    Returns:
        ID de la tâche créée.
    """
    title = title.strip()
    if not title:
        raise ValueError("Le titre est obligatoire.")

    category = "perso" if category == "perso" else "pro"
    absolute_path, relative_path = move_inbox_to_ged(
        inbox_path,
        category=category,
        date_emission=date_emission,
        title=title,
    )

    kanban = compute_kanban_column(completed_at=None, deadline=deadline)
    status = compute_db_status(kanban)

    conn = get_connection()
    try:
        doc_cursor = conn.execute(
            """
            INSERT INTO documents (original_filename, stored_path, mime_type, file_hash)
            VALUES (?, ?, ?, ?)
            """,
            (
                inbox_path.name,
                relative_path,
                guess_mime_type(absolute_path),
                file_sha256(absolute_path),
            ),
        )
        document_id = int(doc_cursor.lastrowid)

        task_cursor = conn.execute(
            """
            INSERT INTO tasks (
                title, category, date_emission, date_event, deadline,
                status, document_id, raw_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                category,
                date_emission.isoformat(),
                date_event.isoformat() if date_event else None,
                deadline.isoformat() if deadline else None,
                status,
                document_id,
                raw_summary.strip() or None,
            ),
        )
        task_id = int(task_cursor.lastrowid)

        tag_ids = _upsert_tags(conn, tags)
        _link_task_tags(conn, task_id, tag_ids)
        conn.commit()
        logger.info("Tâche %s créée — document %s", task_id, relative_path)
        return task_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_tasks(
    *,
    category_filter: str = "all",
    tag_filters: list[str] | None = None,
    include_archived: bool = True,
) -> list[TaskDTO]:
    """Liste les tâches avec filtres catégorie et tags (OR)."""
    query = """
        SELECT
            t.id, t.title, t.category, t.date_emission, t.date_event, t.deadline,
            t.status, t.completed_at, t.document_id, t.raw_summary, t.notes,
            t.calendar_synced, t.calendar_event_id,
            d.stored_path, d.original_filename,
            GROUP_CONCAT(tg.name, ',') AS tag_list
        FROM tasks t
        LEFT JOIN documents d ON d.id = t.document_id
        LEFT JOIN task_tags tt ON tt.task_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        WHERE 1=1
    """
    params: list[object] = []

    if category_filter in ("pro", "perso"):
        query += " AND t.category = ?"
        params.append(category_filter)

    if not include_archived:
        query += " AND t.completed_at IS NULL"

    query += " GROUP BY t.id ORDER BY t.deadline IS NULL, t.deadline ASC, t.created_at DESC"

    conn = get_connection()
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    tasks: list[TaskDTO] = []
    tag_filters_set = {t.lower() for t in (tag_filters or []) if t}

    for row in rows:
        task = _row_to_task(row)
        if tag_filters_set:
            task_tags_lower = {t.lower() for t in task.tags}
            if not task_tags_lower.intersection(tag_filters_set):
                continue
        tasks.append(task)

    return tasks


def _row_to_task(row) -> TaskDTO:
    tags = [t.strip() for t in (row["tag_list"] or "").split(",") if t.strip()]
    return TaskDTO(
        id=int(row["id"]),
        title=str(row["title"]),
        category=str(row["category"]),
        date_emission=date.fromisoformat(str(row["date_emission"])),
        date_event=(
            date.fromisoformat(str(row["date_event"])) if row["date_event"] else None
        ),
        deadline=(date.fromisoformat(str(row["deadline"])) if row["deadline"] else None),
        status=str(row["status"]),
        completed_at=(
            datetime.fromisoformat(str(row["completed_at"]))
            if row["completed_at"]
            else None
        ),
        document_id=int(row["document_id"]) if row["document_id"] else None,
        raw_summary=str(row["raw_summary"]) if row["raw_summary"] else None,
        notes=str(row["notes"]) if row["notes"] else None,
        stored_path=str(row["stored_path"]) if row["stored_path"] else None,
        original_filename=(
            str(row["original_filename"]) if row["original_filename"] else None
        ),
        calendar_synced=bool(row["calendar_synced"]),
        calendar_event_id=(
            str(row["calendar_event_id"]) if row["calendar_event_id"] else None
        ),
        tags=tags,
    )


def get_task_by_id(task_id: int) -> TaskDTO | None:
    query = """
        SELECT
            t.id, t.title, t.category, t.date_emission, t.date_event, t.deadline,
            t.status, t.completed_at, t.document_id, t.raw_summary, t.notes,
            t.calendar_synced, t.calendar_event_id,
            d.stored_path, d.original_filename,
            GROUP_CONCAT(tg.name, ',') AS tag_list
        FROM tasks t
        LEFT JOIN documents d ON d.id = t.document_id
        LEFT JOIN task_tags tt ON tt.task_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        WHERE t.id = ?
        GROUP BY t.id
    """
    conn = get_connection()
    try:
        row = conn.execute(query, (task_id,)).fetchone()
        if row is None:
            return None
        return _row_to_task(row)
    finally:
        conn.close()


def mark_calendar_synced(task_id: int, event_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE tasks
            SET calendar_synced = 1, calendar_event_id = ?,
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (event_id, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_all_tags() -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
        return [str(r["name"]) for r in rows]
    finally:
        conn.close()


def archive_task(task_id: int) -> None:
    """Marque une tâche comme terminée."""
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE tasks
            SET completed_at = ?, status = 'archived', updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def unarchive_task(task_id: int) -> None:
    """Réactive une tâche archivée."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT deadline FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return
        deadline = (
            date.fromisoformat(str(row["deadline"])) if row["deadline"] else None
        )
        kanban = compute_kanban_column(completed_at=None, deadline=deadline)
        status = compute_db_status(kanban)
        conn.execute(
            """
            UPDATE tasks
            SET completed_at = NULL, status = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (status, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_task(
    task_id: int,
    *,
    title: str,
    date_emission: date,
    date_event: date | None,
    deadline: date | None,
    category: str,
    tags: list[str],
    notes: str | None = None,
) -> None:
    """Met à jour une tâche existante (spec §6.3 — Modifier)."""
    title = title.strip()
    if not title:
        raise ValueError("Le titre est obligatoire.")

    category = "perso" if category == "perso" else "pro"
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT completed_at FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Tâche {task_id} introuvable.")

        completed_at = (
            datetime.fromisoformat(str(row["completed_at"]))
            if row["completed_at"]
            else None
        )
        kanban = compute_kanban_column(completed_at=completed_at, deadline=deadline)
        status = compute_db_status(kanban)

        conn.execute(
            """
            UPDATE tasks SET
                title = ?, category = ?, date_emission = ?, date_event = ?,
                deadline = ?, status = ?, notes = ?,
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (
                title,
                category,
                date_emission.isoformat(),
                date_event.isoformat() if date_event else None,
                deadline.isoformat() if deadline else None,
                status,
                notes.strip() if notes else None,
                task_id,
            ),
        )
        tag_ids = _upsert_tags(conn, tags)
        _link_task_tags(conn, task_id, tag_ids)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def refresh_task_statuses() -> None:
    """Recalcule les statuts todo/urgent pour les tâches actives."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, deadline FROM tasks WHERE completed_at IS NULL"
        ).fetchall()
        for row in rows:
            deadline = (
                date.fromisoformat(str(row["deadline"])) if row["deadline"] else None
            )
            kanban = compute_kanban_column(completed_at=None, deadline=deadline)
            status = compute_db_status(kanban)
            conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, row["id"]))
        conn.commit()
    finally:
        conn.close()
