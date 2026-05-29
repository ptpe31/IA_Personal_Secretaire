"""Tests maintenance base SQLite."""

from app.services.db_maintenance import get_application_data_counts, purge_application_data
from app.services.task_service import create_manual_task
from datetime import date


def test_purge_application_data_clears_tasks_keeps_settings():
    create_manual_task(
        title="Tâche à purger",
        category="pro",
        start_date=date(2026, 6, 1),
    )
    counts = get_application_data_counts()
    assert counts["tasks"] >= 1

    removed = purge_application_data()
    assert removed["tasks"] >= 1

    after = get_application_data_counts()
    assert after["tasks"] == 0
    assert after["documents"] == 0

    from app.db.connection import get_setting

    assert get_setting("autopilot_enabled") is not None
