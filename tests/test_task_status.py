"""Tests calcul colonnes Kanban."""

from datetime import date, datetime, timedelta

from app.utils.dates import compute_db_status, compute_kanban_column


def test_archived_when_completed():
    col = compute_kanban_column(
        completed_at=datetime(2026, 5, 29, 10, 0),
        deadline=date(2026, 6, 1),
    )
    assert col == "archived"
    assert compute_db_status(col) == "archived"


def test_no_deadline_goes_to_todo_no_date():
    col = compute_kanban_column(completed_at=None, deadline=None)
    assert col == "todo_no_date"
    assert compute_db_status(col) == "todo"


def test_past_deadline_is_urgent():
    today = date(2026, 5, 29)
    col = compute_kanban_column(
        completed_at=None,
        deadline=date(2026, 5, 28),
        today=today,
    )
    assert col == "urgent"


def test_deadline_within_48h_is_urgent():
    today = date(2026, 5, 29)
    col = compute_kanban_column(
        completed_at=None,
        deadline=today + timedelta(days=1),
        today=today,
    )
    assert col == "urgent"


def test_future_deadline_is_todo():
    today = date(2026, 5, 29)
    col = compute_kanban_column(
        completed_at=None,
        deadline=today + timedelta(days=10),
        today=today,
    )
    assert col == "todo"
