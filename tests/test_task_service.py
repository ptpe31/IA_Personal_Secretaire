"""Tests intégration validation Inbox → GED + SQLite."""

from datetime import date
from pathlib import Path

import pytest

from app.config import PRO_GED_PATH, ROOT_PATH
from app.services.task_service import archive_task, list_tasks, validate_inbox_document


@pytest.fixture
def sample_inbox_file(tmp_path, monkeypatch):
    """Utilise un fichier temporaire ; GED reste sous ~/Trankil-v2."""
    sample = tmp_path / "expo_capture.png"
    sample.write_bytes(b"\x89PNG fake")
    return sample


def test_validate_inbox_creates_task_and_moves_file(sample_inbox_file, monkeypatch):
    inbox_copy = ROOT_PATH / ".inbox" / "test_validate.png"
    inbox_copy.parent.mkdir(parents=True, exist_ok=True)
    inbox_copy.write_bytes(sample_inbox_file.read_bytes())

    task_id = validate_inbox_document(
        inbox_copy,
        title="Mettre à jour Expo",
        date_emission=date(2026, 5, 28),
        date_event=None,
        deadline=date(2026, 6, 26),
        category="pro",
        tags=["Tech", "Expo"],
        raw_summary="Mail maintenance Expo SDK.",
    )

    assert task_id > 0
    assert not inbox_copy.exists()

    ged_file = PRO_GED_PATH / "2026-05-28_Mettre_a_jour_Expo.png"
    assert ged_file.is_file()

    tasks = list_tasks(category_filter="pro")
    match = next((t for t in tasks if t.id == task_id), None)
    assert match is not None
    assert match.title == "Mettre à jour Expo"
    assert match.tags == ["Expo", "Tech"] or set(match.tags) == {"Tech", "Expo"}
    assert match.raw_summary == "Mail maintenance Expo SDK."

    archive_task(task_id)
    archived = next(t for t in list_tasks() if t.id == task_id)
    assert archived.completed_at is not None
