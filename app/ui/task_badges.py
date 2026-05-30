"""Helpers UI — récurrence virtuelle et liens source."""

from __future__ import annotations

from nicegui import ui

from app.models.task import TaskDTO
from app.utils.frequence import FREQUENCE_DISPLAY


def notify_task_completed(task_id: int, result: int | None) -> None:
    """Notification après archivage ou report de récurrence."""
    if result == task_id:
        ui.notify(
            "Échéance reportée — prochaine occurrence planifiée.",
            type="positive",
        )
    elif result:
        ui.notify(
            "Tâche archivée — prochaine occurrence planifiée.",
            type="positive",
        )
    else:
        ui.notify("Tâche archivée.", type="positive")


def render_frequence_icon(task: TaskDTO) -> None:
    if not task.frequence:
        return
    label = FREQUENCE_DISPLAY.get(task.frequence, "Récurrent")
    ui.icon("refresh", size="xs").classes("text-purple-6 shrink-0").tooltip(label)


def render_source_url_link(task: TaskDTO) -> None:
    if not task.source_url:
        return
    ui.link("URL", task.source_url, new_tab=True).classes(
        "text-blue-7 text-xs font-medium shrink-0 hover:underline"
    ).tooltip(task.source_url)
