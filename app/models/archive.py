"""DTO archive GED."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class ArchiveItem:
    """Document archivé avec métadonnées tâche associée."""

    task_id: int
    title: str
    category: str
    date_emission: date
    stored_path: str
    absolute_path: Path
    file_exists: bool
    original_filename: str | None
    raw_summary: str | None
    tags: list[str] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return self.absolute_path.name
