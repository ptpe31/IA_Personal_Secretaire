"""Calcul statut Kanban — spec §4.2."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

KanbanColumn = Literal["archived", "urgent", "todo", "todo_no_date"]


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
