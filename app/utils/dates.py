"""Calcul statut Kanban — spec §4.2."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal, TypeVar

KanbanColumn = Literal["archived", "urgent", "todo", "todo_no_date"]

T = TypeVar("T")


def parse_optional_date(value: str | None) -> date | None:
    """Parse une date ISO ou retourne None si vide."""
    if not value or not str(value).strip():
        return None
    return date.fromisoformat(str(value).strip())


def compute_kanban_column(
    *,
    completed_at: datetime | None,
    deadline: date | None,
    today: date | None = None,
) -> KanbanColumn:
    """Détermine la colonne Kanban d'une tâche."""
    if completed_at is not None:
        return "archived"

    if deadline is None:
        return "todo_no_date"

    ref = today or date.today()
    urgent_threshold = ref + timedelta(hours=48)

    if deadline < ref or deadline <= urgent_threshold:
        return "urgent"

    return "todo"


def compute_db_status(kanban: KanbanColumn) -> str:
    """Mappe la colonne Kanban vers le statut SQLite."""
    if kanban == "archived":
        return "archived"
    if kanban == "urgent":
        return "urgent"
    return "todo"


def format_date_fr(value: date | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d/%m/%Y")


def kanban_batch_sort_key(task: T) -> tuple[int, int | str, int]:
    """Clé de regroupement : lot document ou création manuelle (même seconde)."""
    doc_id = getattr(task, "document_id", None)
    if doc_id is not None:
        return (0, doc_id, 0)
    created_at = getattr(task, "created_at", None)
    if created_at is not None:
        stamp = created_at.replace(microsecond=0).isoformat()
        return (1, stamp, 0)
    return (2, getattr(task, "id", 0), 0)


def sort_kanban_urgent(tasks: list[T]) -> list[T]:
    """Tri urgent : lot regroupé, puis deadline ASC (plus ancienne en haut)."""
    return sorted(
        tasks,
        key=lambda task: (
            kanban_batch_sort_key(task),
            task.deadline or date.max,
            getattr(task, "id", 0),
        ),
    )


def sort_kanban_todo(tasks: list[T]) -> list[T]:
    """Tri à faire : lot regroupé, puis deadline ASC (sans date en bas du bucket)."""
    return sorted(
        tasks,
        key=lambda task: (
            kanban_batch_sort_key(task),
            task.deadline is None,
            task.deadline or date.max,
            getattr(task, "id", 0),
        ),
    )


def sort_kanban_no_date(tasks: list[T]) -> list[T]:
    """Tri sans date : lot regroupé, puis ordre de création."""
    return sorted(
        tasks,
        key=lambda task: (
            kanban_batch_sort_key(task),
            getattr(task, "created_at", None) or datetime.min,
            getattr(task, "id", 0),
        ),
    )


def sort_list_view_tasks(tasks: list[T]) -> list[T]:
    """Tri vue Liste : lots regroupés, échéances proches en haut, sans date en bas."""
    return sorted(
        tasks,
        key=lambda task: (
            kanban_batch_sort_key(task),
            task.deadline is None,
            task.deadline or date.max,
            getattr(task, "id", 0),
        ),
    )


_WEEKDAYS_FR = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)

_MONTHS_FR = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def compute_menu_week_sunday(today: date | None = None) -> date:
    """Dimanche de référence : aujourd'hui si dimanche, sinon le prochain dimanche."""
    ref = today or date.today()
    if ref.weekday() == 6:
        return ref
    return ref + timedelta(days=6 - ref.weekday())


def format_today_anchor(today: date | None = None) -> str:
    """Ancrage temporel injecté dans le prompt Ollama."""
    ref = today or date.today()
    weekday = _WEEKDAYS_FR[ref.weekday()]
    month = _MONTHS_FR[ref.month - 1]
    return f"Aujourd'hui nous sommes le {weekday} {ref.day} {month} {ref.year}."
