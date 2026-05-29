"""DTO tâche pour l'UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class TaskDTO:
    id: int
    title: str
    category: str
    date_emission: date
    date_event: date | None
    deadline: date | None
    status: str
    completed_at: datetime | None
    document_id: int | None
    raw_summary: str | None
    notes: str | None
    stored_path: str | None
    original_filename: str | None
    tags: list[str] = field(default_factory=list)
