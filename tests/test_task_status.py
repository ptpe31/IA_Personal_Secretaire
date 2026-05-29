"""Tests calcul colonnes Kanban."""

from datetime import date, datetime, timedelta

from app.utils.dates import compute_db_status, compute_kanban_column, sort_kanban_todo, sort_kanban_urgent


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


class _TaskStub:
    def __init__(self, deadline: date | None) -> None:
        self.deadline = deadline


def test_sort_kanban_urgent_oldest_first():
    tasks = [
        _TaskStub(date(2026, 5, 28)),
        _TaskStub(date(2026, 5, 1)),
        _TaskStub(date(2026, 5, 15)),
    ]
    sorted_tasks = sort_kanban_urgent(tasks)
    assert [t.deadline for t in sorted_tasks] == [
        date(2026, 5, 1),
        date(2026, 5, 15),
        date(2026, 5, 28),
    ]


def test_sort_kanban_todo_nearest_first_null_last():
    tasks = [
        _TaskStub(date(2026, 6, 15)),
        _TaskStub(None),
        _TaskStub(date(2026, 6, 1)),
        _TaskStub(None),
    ]
    sorted_tasks = sort_kanban_todo(tasks)
    assert [t.deadline for t in sorted_tasks] == [
        date(2026, 6, 1),
        date(2026, 6, 15),
        None,
        None,
    ]
