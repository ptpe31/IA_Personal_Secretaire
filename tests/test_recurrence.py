"""Tests tâches manuelles et récurrence."""

from datetime import date

import pytest

from app.services.task_service import archive_task, create_manual_task, get_task_by_id, list_tasks
from app.utils.recurrence import compute_next_occurrence


def test_compute_next_occurrence_daily():
    assert compute_next_occurrence(date(2026, 5, 29), "daily") == date(2026, 5, 30)


def test_compute_next_occurrence_weekly():
    assert compute_next_occurrence(date(2026, 5, 29), "weekly") == date(2026, 6, 5)


def test_compute_next_occurrence_monthly():
    assert compute_next_occurrence(date(2026, 5, 29), "monthly") == date(2026, 6, 29)


def test_compute_next_occurrence_monthly_end_of_month():
    assert compute_next_occurrence(date(2026, 1, 31), "monthly") == date(2026, 2, 28)


def test_create_manual_task_without_recurrence():
    task_id = create_manual_task(
        title="Tâche manuelle test",
        category="pro",
        start_date=date(2026, 6, 15),
        suggestion="Note optionnelle",
    )
    task = get_task_by_id(task_id)
    assert task is not None
    assert task.title == "Tâche manuelle test"
    assert task.category == "pro"
    assert task.deadline == date(2026, 6, 15)
    assert task.recurrence_pattern is None
    assert task.parent_task_id is None
    assert task.suggestion == "Note optionnelle"
    assert task.document_id is None


def test_create_manual_task_with_monthly_recurrence():
    task_id = create_manual_task(
        title="Tâche récurrente mensuelle",
        category="perso",
        start_date=date(2026, 6, 1),
        recurrence_pattern="monthly",
    )
    task = get_task_by_id(task_id)
    assert task is not None
    assert task.recurrence_pattern == "monthly"


def test_archive_spawns_next_monthly_occurrence():
    task_id = create_manual_task(
        title="Occurrence mensuelle",
        category="pro",
        start_date=date(2026, 6, 10),
        recurrence_pattern="monthly",
        suggestion="Note test",
    )
    spawned_id = archive_task(task_id)
    assert spawned_id is not None
    assert spawned_id != task_id

    archived = get_task_by_id(task_id)
    assert archived is not None
    assert archived.completed_at is not None

    next_task = get_task_by_id(spawned_id)
    assert next_task is not None
    assert next_task.title == "Occurrence mensuelle"
    assert next_task.category == "pro"
    assert next_task.deadline == date(2026, 7, 10)
    assert next_task.recurrence_pattern == "monthly"
    assert next_task.parent_task_id == task_id
    assert next_task.suggestion == "Note test"
    assert next_task.completed_at is None


def test_archive_non_recurring_returns_none():
    task_id = create_manual_task(
        title="Tâche ponctuelle",
        category="pro",
        start_date=date(2026, 6, 10),
    )
    assert archive_task(task_id) is None


def test_recurrence_chain_preserves_root_parent():
    root_id = create_manual_task(
        title="Occurrence hebdomadaire",
        category="pro",
        start_date=date(2026, 6, 1),
        recurrence_pattern="weekly",
    )
    second_id = archive_task(root_id)
    assert second_id is not None

    third_id = archive_task(second_id)
    assert third_id is not None

    third = get_task_by_id(third_id)
    assert third is not None
    assert third.parent_task_id == root_id
    assert third.deadline == date(2026, 6, 15)


def test_create_manual_task_requires_title():
    with pytest.raises(ValueError, match="titre"):
        create_manual_task(
            title="  ",
            category="pro",
            start_date=date(2026, 6, 1),
        )
