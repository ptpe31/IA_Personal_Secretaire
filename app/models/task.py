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
    calendar_synced: bool = False
    calendar_event_id: str | None = None
    suggestion: str | None = None
    recurrence_pattern: str | None = None
    frequence: str | None = None
    date_reference: date | None = None
    source_url: str | None = None
    parent_task_id: int | None = None
    created_at: datetime | None = None
    tags: list[str] = field(default_factory=list)
