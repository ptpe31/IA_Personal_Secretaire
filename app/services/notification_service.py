"""Relances anti-oubli macOS — spec §8.1."""

from __future__ import annotations

import logging
import subprocess
from datetime import date
from typing import Literal

from app.config import APP_TITLE
from app.db.connection import get_connection, get_setting

logger = logging.getLogger(__name__)

NotificationType = Literal["j_minus_3", "j_minus_1"]


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def send_macos_notification(title: str, message: str) -> bool:
    """Envoie une notification native macOS via osascript."""
    script = (
        f'display notification "{_escape_applescript(message)}" '
        f'with title "{_escape_applescript(title)}"'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning("Notification macOS échouée : %s", result.stderr.strip())
            return False
        return True
    except OSError as exc:
        logger.error("Impossible d'envoyer la notification : %s", exc)
        return False


def days_until_deadline(deadline: date, today: date | None = None) -> int:
    """Nombre de jours calendaires avant la deadline (0 = aujourd'hui)."""
    ref = today or date.today()
    return (deadline - ref).days


def notification_type_for_days(days: int) -> NotificationType | None:
    if days == 3:
        return "j_minus_3"
    if days == 1:
        return "j_minus_1"
    return None


def _already_sent(task_id: int, notification_type: NotificationType) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT 1 FROM notifications_log
            WHERE task_id = ? AND notification_type = ?
            """,
            (task_id, notification_type),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _log_sent(task_id: int, notification_type: NotificationType) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO notifications_log (task_id, notification_type)
            VALUES (?, ?)
            """,
            (task_id, notification_type),
        )
        conn.commit()
    finally:
        conn.close()


def build_reminder_message(title: str, days: int) -> str:
    if days == 1:
        return f'Il te reste 1 jour pour « {title} ».'
    return f'Il te reste {days} jours pour « {title} ».'


def process_deadline_reminders(*, today: date | None = None) -> int:
    """
    Vérifie les tâches actives et envoie les notifications J-3 / J-1.

    Returns:
        Nombre de notifications envoyées.
    """
    if get_setting("notification_enabled", "true") != "true":
        return 0

    ref = today or date.today()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, title, deadline
            FROM tasks
            WHERE completed_at IS NULL AND deadline IS NOT NULL
            """
        ).fetchall()
    finally:
        conn.close()

    sent = 0
    for row in rows:
        task_id = int(row["id"])
        title = str(row["title"])
        deadline = date.fromisoformat(str(row["deadline"]))
        days = days_until_deadline(deadline, ref)
        notif_type = notification_type_for_days(days)
        if notif_type is None:
            continue
        if _already_sent(task_id, notif_type):
            continue

        message = build_reminder_message(title, days)
        if send_macos_notification(f"⚠️ {APP_TITLE}", message):
            _log_sent(task_id, notif_type)
            sent += 1
            logger.info("Notification %s envoyée pour tâche %s", notif_type, task_id)

    return sent
