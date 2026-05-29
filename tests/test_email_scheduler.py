"""Tests relances email J-1."""

from datetime import date, timedelta
from unittest.mock import patch

from app.db.connection import get_connection, init_db
from app.services.email_scheduler import (
    TaskReminder,
    build_email_body,
    build_email_subject,
    find_tasks_due_tomorrow,
    process_email_reminders,
)


def test_build_email_subject_single_task():
    tasks = [TaskReminder(task_id=1, title="Payer loyer", deadline=date(2026, 5, 30))]
    subject = build_email_subject(tasks)
    assert "Payer loyer" in subject
    assert "Secrétaire iA_Rappel" in subject


def test_build_email_subject_multiple_tasks():
    tasks = [
        TaskReminder(task_id=1, title="A", deadline=date(2026, 5, 30)),
        TaskReminder(task_id=2, title="B", deadline=date(2026, 5, 30)),
    ]
    assert "2 tâches" in build_email_subject(tasks)


def test_build_email_body_lists_all_tasks():
    tasks = [
        TaskReminder(task_id=1, title="A", deadline=date(2026, 5, 30)),
        TaskReminder(task_id=2, title="B", deadline=date(2026, 5, 30)),
    ]
    body = build_email_body(tasks)
    assert "A" in body
    assert "B" in body
    assert "1." in body
    assert "2." in body


def test_find_tasks_due_tomorrow():
    init_db(force=True)
    tomorrow = date.today() + timedelta(days=1)
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO tasks (title, category, date_emission, deadline, status)
            VALUES ('Demain', 'pro', ?, ?, 'todo')
            """,
            (date.today().isoformat(), tomorrow.isoformat()),
        )
        conn.execute(
            """
            INSERT INTO tasks (title, category, date_emission, deadline, status, completed_at)
            VALUES ('Archivée', 'pro', ?, ?, 'archived', datetime('now'))
            """,
            (date.today().isoformat(), tomorrow.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    tasks = find_tasks_due_tomorrow(today=date.today())
    assert len(tasks) == 1
    assert tasks[0].title == "Demain"


def test_process_email_reminders_skips_when_disabled():
    init_db(force=True)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE settings SET value = 'false' WHERE key = 'email_reminder_enabled'"
        )
        conn.commit()
    finally:
        conn.close()
    assert process_email_reminders(today=date.today()) == 0


def test_process_email_reminders_sends_once_per_day():
    init_db(force=True)
    tomorrow = date.today() + timedelta(days=1)
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO tasks (title, category, date_emission, deadline, status)
            VALUES ('Relance test', 'pro', ?, ?, 'urgent')
            """,
            (date.today().isoformat(), tomorrow.isoformat()),
        )
        conn.execute(
            "UPDATE settings SET value = 'test@example.com' WHERE key = 'sender_email'"
        )
        conn.execute(
            "UPDATE settings SET value = 'test@example.com' WHERE key = 'recipient_email'"
        )
        conn.commit()
    finally:
        conn.close()

    fake_config = type(
        "Cfg",
        (),
        {
            "enabled": True,
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "sender_email": "test@example.com",
            "recipient_email": "test@example.com",
            "app_password": "app-pass",
        },
    )()

    with (
        patch("app.services.email_scheduler.get_email_config", return_value=fake_config),
        patch("app.services.email_scheduler.send_reminder_email") as send_mock,
    ):
        assert process_email_reminders(today=date.today()) == 1
        send_mock.assert_called_once()
        assert process_email_reminders(today=date.today()) == 0
