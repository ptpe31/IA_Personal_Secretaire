"""Tests titres événements Google Calendar."""

from datetime import date

from app.models.task import TaskDTO
from app.services.calendar_service import build_event_description, build_event_title


def test_build_event_title_pro():
    task = TaskDTO(
        id=1,
        title="Mettre à jour Expo",
        category="pro",
        date_emission=date(2026, 5, 28),
        date_event=None,
        deadline=date(2026, 6, 26),
        status="todo",
        completed_at=None,
        document_id=1,
        raw_summary="Mail Expo",
        notes=None,
        stored_path="Pro/GED/x.png",
        original_filename="x.png",
        tags=["Tech", "Expo"],
    )
    title = build_event_title(task)
    assert title.startswith("[PRO]")
    assert "Mettre à jour Expo" in title
    assert "26 Juin" in title


def test_build_event_description_includes_tags():
    task = TaskDTO(
        id=1,
        title="TVA",
        category="pro",
        date_emission=date(2026, 5, 1),
        date_event=None,
        deadline=date(2026, 6, 15),
        status="todo",
        completed_at=None,
        document_id=1,
        raw_summary=None,
        notes=None,
        stored_path=None,
        original_filename=None,
        tags=["Compta", "TVA"],
    )
    desc = build_event_description(task)
    assert "01/05/2026" in desc
    assert "#Compta" in desc
