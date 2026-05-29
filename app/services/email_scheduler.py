"""Relances proactives par email (J-1) — SMTP Gmail."""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from datetime import date, timedelta
from email.mime.text import MIMEText

from app.config import get_email_config
from app.db.connection import get_connection, get_setting, set_setting
from app.utils.dates import format_date_fr

logger = logging.getLogger(__name__)

_LAST_SENT_SETTING = "email_reminder_last_sent_date"


@dataclass(frozen=True)
class TaskReminder:
    task_id: int
    title: str
    deadline: date


def _is_enabled() -> bool:
    if get_setting("notification_enabled", "true") != "true":
        return False
    if get_setting("email_reminder_enabled", "true") != "true":
        return False
    config = get_email_config()
    return config.enabled and bool(config.sender_email) and bool(config.app_password)


def _already_sent_today(today: date) -> bool:
    return get_setting(_LAST_SENT_SETTING) == today.isoformat()


def _mark_sent_today(today: date) -> None:
    set_setting(_LAST_SENT_SETTING, today.isoformat())


def _log_task_reminder(task_id: int, reminder_date: date) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO email_reminders_log (task_id, reminder_date)
            VALUES (?, ?)
            """,
            (task_id, reminder_date.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def find_tasks_due_tomorrow(*, today: date | None = None) -> list[TaskReminder]:
    """Tâches actives dont l'échéance est demain (J-1)."""
    ref = today or date.today()
    tomorrow = ref + timedelta(days=1)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, title, deadline
            FROM tasks
            WHERE completed_at IS NULL
              AND status IN ('todo', 'urgent')
              AND deadline = ?
            ORDER BY deadline ASC, id ASC
            """,
            (tomorrow.isoformat(),),
        ).fetchall()
    finally:
        conn.close()

    return [
        TaskReminder(
            task_id=int(row["id"]),
            title=str(row["title"]),
            deadline=date.fromisoformat(str(row["deadline"])),
        )
        for row in rows
    ]


def build_email_subject(tasks: list[TaskReminder]) -> str:
    if len(tasks) == 1:
        return (
            f"🚨 Secrétaire iA_Rappel : Tâche urgente pour demain - {tasks[0].title}"
        )
    return f"🚨 Secrétaire iA_Rappel : {len(tasks)} tâches urgentes pour demain"


def build_email_body(tasks: list[TaskReminder]) -> str:
    if len(tasks) == 1:
        task = tasks[0]
        return (
            f"Coucou ! Petit rappel pour ta tâche : {task.title}. "
            f"Échéance prévue le {format_date_fr(task.deadline)}. "
            "N'oublie pas de la traiter !"
        )

    lines = [
        "Coucou ! Petit rappel — voici tes tâches pour demain :",
        "",
    ]
    for index, task in enumerate(tasks, start=1):
        lines.append(
            f"{index}. {task.title} — échéance le {format_date_fr(task.deadline)}"
        )
    lines.extend(["", "N'oublie pas de les traiter !"])
    return "\n".join(lines)


def send_reminder_email(
    *,
    tasks: list[TaskReminder],
    smtp_server: str,
    smtp_port: int,
    sender_email: str,
    recipient_email: str,
    app_password: str,
) -> None:
    message = MIMEText(build_email_body(tasks), "plain", "utf-8")
    message["Subject"] = build_email_subject(tasks)
    message["From"] = sender_email
    message["To"] = recipient_email

    with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(sender_email, app_password)
        smtp.sendmail(sender_email, [recipient_email], message.as_string())


def process_email_reminders(*, today: date | None = None) -> int:
    """
    Envoie un email récapitulatif pour les tâches échéant demain (une fois par jour).

    Returns:
        1 si un email a été envoyé, 0 sinon.
    """
    ref = today or date.today()

    try:
        if not _is_enabled():
            return 0
        if _already_sent_today(ref):
            return 0

        tasks = find_tasks_due_tomorrow(today=ref)
        if not tasks:
            return 0

        config = get_email_config()
        if not config.app_password:
            logger.warning("Relance email ignorée : SMTP_APP_PASSWORD manquant.")
            return 0

        recipient = config.recipient_email or config.sender_email
        send_reminder_email(
            tasks=tasks,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            sender_email=config.sender_email,
            recipient_email=recipient,
            app_password=config.app_password,
        )

        _mark_sent_today(ref)
        for task in tasks:
            _log_task_reminder(task.task_id, ref)
            logger.info("Relance email J-1 enregistrée pour tâche %s", task.task_id)

        logger.info(
            "Email de relance envoyé (%s tâche(s)) à %s.",
            len(tasks),
            recipient,
        )
        return 1
    except (OSError, smtplib.SMTPException, TimeoutError) as exc:
        logger.warning("Relance email impossible (réseau/SMTP) : %s", exc)
        return 0
    except Exception:
        logger.exception("Erreur inattendue lors de la relance email")
        return 0
