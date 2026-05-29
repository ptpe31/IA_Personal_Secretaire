"""Tests intégration validation Inbox → GED + SQLite."""

from datetime import date
from pathlib import Path

import pytest

from app.config import PRO_GED_PATH, ROOT_PATH
from app.services.task_service import (
    TaskValidationInput,
    archive_task,
    list_tasks,
    validate_inbox_document,
    validate_inbox_tasks,
)


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
    assert set(match.tags) == {"tech", "expo"}
    assert match.raw_summary == "Mail maintenance Expo SDK."

    archive_task(task_id)
    archived = next(t for t in list_tasks() if t.id == task_id)
    assert archived.completed_at is not None


def test_validate_inbox_multi_tasks_one_document(sample_inbox_file):
    inbox_copy = ROOT_PATH / ".inbox" / "test_multi.png"
    inbox_copy.parent.mkdir(parents=True, exist_ok=True)
    inbox_copy.write_bytes(sample_inbox_file.read_bytes())

    task_ids = validate_inbox_tasks(
        inbox_copy,
        [
            TaskValidationInput(
                title="Répétition Hip-Hop 1/4",
                date_emission=date(2026, 5, 26),
                date_event=date(2026, 6, 4),
                deadline=date(2026, 6, 4),
                category="perso",
                tags=["danse", "hiphop"],
                raw_summary="Mail service culturel",
                justification_proof="le 4 juin de 18h à 19h",
            ),
            TaskValidationInput(
                title="Spectacle Hip-Hop",
                date_emission=date(2026, 5, 26),
                date_event=date(2026, 6, 27),
                deadline=date(2026, 6, 27),
                category="perso",
                tags=["spectacle", "danse"],
                raw_summary="Mail service culturel",
                justification_proof="samedi 27 juin 2026",
            ),
        ],
        ged_title="Mail_Culturel_HipHop",
        ged_category="perso",
        ged_date_emission=date(2026, 5, 26),
        document_summary="Mail service culturel hip-hop",
    )

    assert len(task_ids) == 2
    assert not inbox_copy.exists()

    tasks = list_tasks(category_filter="perso")
    created = [t for t in tasks if t.id in task_ids]
    assert len(created) == 2
    assert created[0].document_id == created[1].document_id
    assert created[0].document_id is not None
