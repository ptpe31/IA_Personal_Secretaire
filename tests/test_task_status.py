"""Tests calcul colonnes Kanban."""

from datetime import date, datetime, timedelta

from app.utils.dates import (
    compute_db_status,
    compute_kanban_column,
    kanban_batch_sort_key,
    sort_kanban_todo,
    sort_kanban_urgent,
)


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


class _BatchTaskStub:
    def __init__(
        self,
        *,
        task_id: int,
        deadline: date | None,
        document_id: int | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self.id = task_id
        self.deadline = deadline
        self.document_id = document_id
        self.created_at = created_at


def test_kanban_sort_groups_sibling_document_tasks():
    tasks = [
        _BatchTaskStub(task_id=3, deadline=date(2026, 6, 15), document_id=10),
        _BatchTaskStub(task_id=1, deadline=date(2026, 6, 1), document_id=10),
        _BatchTaskStub(task_id=2, deadline=date(2026, 6, 5), document_id=11),
    ]
    sorted_tasks = sort_kanban_todo(tasks)
    assert [t.id for t in sorted_tasks] == [1, 3, 2]


def test_kanban_sort_groups_manual_tasks_same_creation_second():
    ts = datetime(2026, 5, 29, 16, 41, 22)
    tasks = [
        _BatchTaskStub(task_id=2, deadline=date(2026, 6, 10), created_at=ts),
        _BatchTaskStub(task_id=1, deadline=date(2026, 6, 1), created_at=ts),
        _BatchTaskStub(
            task_id=3,
            deadline=date(2026, 6, 5),
            created_at=datetime(2026, 5, 29, 16, 42, 0),
        ),
    ]
    sorted_tasks = sort_kanban_todo(tasks)
    assert [t.id for t in sorted_tasks] == [1, 2, 3]
    assert kanban_batch_sort_key(tasks[0]) == kanban_batch_sort_key(tasks[1])
