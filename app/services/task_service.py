"""Service métier tâches, tags et validation Inbox."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.db.connection import get_connection
from app.models.task import TaskDTO
from app.services.ged_service import file_sha256, guess_mime_type, move_inbox_to_ged
from app.utils.analysis_logging import log_tasks_validated
from app.utils.dates import compute_db_status, compute_kanban_column, parse_optional_date
from app.utils.frequence import FREQUENCE_VALUES, calculer_prochaine_echeance
from app.utils.recurrence import RECURRENCE_PATTERNS, compute_next_occurrence
from app.utils.tags import normalize_tags

logger = logging.getLogger(__name__)


@dataclass
class TaskValidationInput:
    title: str
    date_emission: date
    date_event: date | None
    deadline: date | None
    category: str
    tags: list[str]
    raw_summary: str = ""
    justification_proof: str | None = None
    suggestion: str | None = None
    frequence: str | None = None
    source_url: str | None = None


def parse_tags_input(raw: str) -> list[str]:
    """Parse tags séparés par virgules."""
    return normalize_tags(raw)


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


def validate_inbox_tasks(
    inbox_path: Path,
    tasks: list[TaskValidationInput],
    *,
    ged_title: str,
    ged_category: str,
    ged_date_emission: date,
    document_summary: str = "",
) -> list[int]:
    """
    Valide un document Inbox : un fichier GED, un documents, N tasks.

    Returns:
        IDs des tâches créées.
    """
    if not tasks:
        raise ValueError("Au moins une tâche est requise.")

    ged_title = ged_title.strip()
    if not ged_title:
        raise ValueError("Le titre GED est obligatoire.")

    ged_category = "perso" if ged_category == "perso" else "pro"
    absolute_path, relative_path = move_inbox_to_ged(
        inbox_path,
        category=ged_category,
        date_emission=ged_date_emission,
        title=ged_title,
    )

    conn = get_connection()
    task_ids: list[int] = []
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

        summary = document_summary.strip()
        for item in tasks:
            title = item.title.strip()
            if not title:
                raise ValueError("Chaque tâche doit avoir un titre.")

            category = "perso" if item.category == "perso" else "pro"
            kanban = compute_kanban_column(completed_at=None, deadline=item.deadline)
            status = compute_db_status(kanban)
            proof = (item.justification_proof or "").strip() or None
            task_summary = item.raw_summary.strip() or summary or None
            suggestion = (item.suggestion or "").strip() or None

            task_cursor = conn.execute(
                """
                INSERT INTO tasks (
                    title, category, date_emission, date_event, deadline,
                    status, document_id, raw_summary, justification_proof, suggestion,
                    frequence, source_url, date_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    category,
                    item.date_emission.isoformat(),
                    item.date_event.isoformat() if item.date_event else None,
                    item.deadline.isoformat() if item.deadline else None,
                    status,
                    document_id,
                    task_summary,
                    proof,
                    suggestion,
                    item.frequence,
                    (item.source_url or "").strip() or None,
                    (
                        (item.deadline or item.date_event or item.date_emission).isoformat()
                        if item.frequence
                        else None
                    ),
                ),
            )
            task_id = int(task_cursor.lastrowid)
            task_ids.append(task_id)

            tag_ids = _upsert_tags(conn, normalize_tags(item.tags))
            _link_task_tags(conn, task_id, tag_ids)

        conn.commit()
        log_tasks_validated(
            logger,
            filename=inbox_path.name,
            document_id=document_id,
            ged_path=relative_path,
            document_summary=summary,
            tasks=tasks,
            task_ids=task_ids,
        )
        return task_ids
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
    justification_proof: str | None = None,
    suggestion: str | None = None,
) -> int:
    """
    Valide un document Inbox (mono-tâche, rétrocompatibilité).

    Returns:
        ID de la tâche créée.
    """
    ids = validate_inbox_tasks(
        inbox_path,
        [
            TaskValidationInput(
                title=title,
                date_emission=date_emission,
                date_event=date_event,
                deadline=deadline,
                category=category,
                tags=tags,
                raw_summary=raw_summary,
                justification_proof=justification_proof,
                suggestion=suggestion,
            )
        ],
        ged_title=title,
        ged_category=category,
        ged_date_emission=date_emission,
        document_summary=raw_summary,
    )
    return ids[0]


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
            t.status, t.completed_at, t.document_id, t.created_at, t.raw_summary, t.notes,
            t.suggestion, t.recurrence_pattern, t.frequence, t.date_reference,
            t.source_url, t.parent_task_id,
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
        created_at=(
            datetime.fromisoformat(str(row["created_at"])) if row["created_at"] else None
        ),
        raw_summary=str(row["raw_summary"]) if row["raw_summary"] else None,
        notes=str(row["notes"]) if row["notes"] else None,
        suggestion=str(row["suggestion"]) if row["suggestion"] else None,
        recurrence_pattern=(
            str(row["recurrence_pattern"]) if row["recurrence_pattern"] else None
        ),
        frequence=str(row["frequence"]) if row["frequence"] else None,
        date_reference=(
            date.fromisoformat(str(row["date_reference"]))
            if row["date_reference"]
            else None
        ),
        source_url=str(row["source_url"]).strip() if row["source_url"] else None,
        parent_task_id=(
            int(row["parent_task_id"]) if row["parent_task_id"] else None
        ),
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
            t.status, t.completed_at, t.document_id, t.created_at, t.raw_summary, t.notes,
            t.suggestion, t.recurrence_pattern, t.frequence, t.date_reference,
            t.source_url, t.parent_task_id,
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


def create_manual_task(
    *,
    title: str,
    category: str,
    start_date: date,
    recurrence_pattern: str | None = None,
    suggestion: str | None = None,
) -> int:
    """Crée une tâche manuelle (sans document GED)."""
    title = title.strip()
    if not title:
        raise ValueError("Le titre est obligatoire.")

    category = "perso" if category == "perso" else "pro"
    if recurrence_pattern is not None and recurrence_pattern not in RECURRENCE_PATTERNS:
        raise ValueError(f"Récurrence invalide : {recurrence_pattern}")

    today = date.today()
    kanban = compute_kanban_column(completed_at=None, deadline=start_date)
    status = compute_db_status(kanban)
    suggestion_text = suggestion.strip() if suggestion else None

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO tasks (
                title, category, date_emission, date_event, deadline,
                status, suggestion, recurrence_pattern
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                category,
                today.isoformat(),
                start_date.isoformat(),
                start_date.isoformat(),
                status,
                suggestion_text,
                recurrence_pattern,
            ),
        )
        task_id = int(cursor.lastrowid)
        conn.commit()
        logger.info(
            "Tâche manuelle créée — id=%s titre=%r récurrence=%s",
            task_id,
            title,
            recurrence_pattern,
        )
        return task_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _spawn_recurrence_task(conn, row) -> int | None:
    """Insère la prochaine occurrence d'une tâche récurrente archivée."""
    pattern = row["recurrence_pattern"]
    if not pattern or pattern not in RECURRENCE_PATTERNS:
        return None

    reference = row["deadline"] or row["date_event"] or row["date_emission"]
    if not reference:
        return None

    base_date = date.fromisoformat(str(reference))
    next_deadline = compute_next_occurrence(base_date, str(pattern))
    root_id = int(row["parent_task_id"]) if row["parent_task_id"] else int(row["id"])

    kanban = compute_kanban_column(completed_at=None, deadline=next_deadline)
    status = compute_db_status(kanban)
    today = date.today()

    cursor = conn.execute(
        """
        INSERT INTO tasks (
            title, category, date_emission, date_event, deadline,
            status, suggestion, recurrence_pattern, parent_task_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(row["title"]),
            str(row["category"]),
            today.isoformat(),
            next_deadline.isoformat(),
            next_deadline.isoformat(),
            status,
            row["suggestion"],
            pattern,
            root_id,
        ),
    )
    return int(cursor.lastrowid)


def _advance_virtual_recurrence(conn, row) -> None:
    """Reporte l'échéance d'une tâche récurrente virtuelle (même ligne SQLite)."""
    frequence = row["frequence"]
    if not frequence or frequence not in FREQUENCE_VALUES:
        return

    reference = row["deadline"] or row["date_event"] or row["date_emission"]
    if not reference:
        return

    base_date = date.fromisoformat(str(reference))
    next_deadline = calculer_prochaine_echeance(base_date, str(frequence))
    kanban = compute_kanban_column(completed_at=None, deadline=next_deadline)
    status = compute_db_status(kanban)
    date_ref = row["date_reference"] or reference

    conn.execute(
        """
        UPDATE tasks
        SET deadline = ?, date_event = ?, status = ?, completed_at = NULL,
            date_reference = ?, updated_at = datetime('now', 'localtime')
        WHERE id = ?
        """,
        (
            next_deadline.isoformat(),
            next_deadline.isoformat(),
            status,
            str(date_ref),
            int(row["id"]),
        ),
    )


def archive_task(task_id: int) -> int | None:
    """
    Marque une tâche comme terminée ou reporte une récurrence virtuelle.

    Returns:
        - task_id si récurrence virtuelle (même ligne mise à jour)
        - nouvel ID si récurrence classique (spawn)
        - None si archivage simple
    """
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT id, title, category, date_emission, date_event, deadline,
                   suggestion, recurrence_pattern, frequence, date_reference,
                   parent_task_id
            FROM tasks WHERE id = ?
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Tâche {task_id} introuvable.")

        if row["frequence"]:
            _advance_virtual_recurrence(conn, row)
            conn.commit()
            logger.info(
                "Récurrence virtuelle — tâche %s reportée (%s)",
                task_id,
                row["frequence"],
            )
            return task_id

        conn.execute(
            """
            UPDATE tasks
            SET completed_at = ?, status = 'archived',
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (now, task_id),
        )
        spawned_id = _spawn_recurrence_task(conn, row)
        conn.commit()
        if spawned_id:
            logger.info(
                "Récurrence — tâche %s archivée, prochaine occurrence %s",
                task_id,
                spawned_id,
            )
        return spawned_id
    except Exception:
        conn.rollback()
        raise
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


def delete_task(task_id: int) -> None:
    """Supprime définitivement une tâche de la base (tags et notifications associés inclus)."""
    delete_tasks([task_id])


def delete_tasks(task_ids: list[int]) -> int:
    """Supprime définitivement plusieurs tâches en une transaction."""
    if not task_ids:
        return 0
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(task_ids))
        cursor = conn.execute(
            f"DELETE FROM tasks WHERE id IN ({placeholders})",
            task_ids,
        )
        deleted = int(cursor.rowcount)
        if deleted == 0:
            raise ValueError("Aucune tâche supprimée.")
        conn.commit()
        logger.info("%s tâche(s) supprimée(s)", deleted)
        return deleted
    except Exception:
        conn.rollback()
        raise
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
    suggestion: str | None = None,
    frequence: str | None = None,
    source_url: str | None = None,
) -> None:
    """Met à jour une tâche existante (spec §6.3 — Modifier)."""
    title = title.strip()
    if not title:
        raise ValueError("Le titre est obligatoire.")

    if frequence is not None and frequence not in FREQUENCE_VALUES:
        raise ValueError(f"Fréquence invalide : {frequence}")

    category = "perso" if category == "perso" else "pro"
    url_clean = (source_url or "").strip() or None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT completed_at, date_reference FROM tasks WHERE id = ?",
            (task_id,),
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
        date_ref = row["date_reference"]
        if frequence and not date_ref:
            ref = deadline or date_event or date_emission
            date_ref = ref.isoformat() if ref else None
        elif not frequence:
            date_ref = None

        conn.execute(
            """
            UPDATE tasks SET
                title = ?, category = ?, date_emission = ?, date_event = ?,
                deadline = ?, status = ?, notes = ?, suggestion = ?,
                frequence = ?, source_url = ?, date_reference = ?,
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
                suggestion.strip() if suggestion else None,
                frequence,
                url_clean,
                date_ref,
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
