"""Bouton sync Google Calendar réutilisable."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from nicegui import ui

from app.models.task import TaskDTO
from app.services.calendar_service import CalendarService


def add_calendar_sync_button(
    task: TaskDTO,
    *,
    on_synced: Callable[[], None] | None = None,
) -> None:
    """Ajoute le bouton Synchroniser l'agenda sur une carte tâche."""
    if task.deadline is None:
        return

    calendar = CalendarService()
    if task.calendar_synced:
        ui.icon("event_available", color="green").classes("text-sm").tooltip(
            "Synchronisé avec Google Calendar"
        )
        return

    async def sync() -> None:
        if not calendar.is_configured():
            ui.notify(
                "Google Calendar non configuré — voir l'onglet Paramètres.",
                type="warning",
            )
            return
        try:
            await asyncio.to_thread(calendar.sync_task, task)
            ui.notify("Événement créé dans Google Calendar.", type="positive")
            if on_synced:
                on_synced()
        except Exception as exc:
            ui.notify(f"Sync Calendar échouée : {exc}", type="negative")

    ui.button(icon="event", on_click=sync).props("flat round dense size=sm").classes(
        "trankil-icon-btn"
    ).tooltip(
        "Synchroniser l'agenda"
    )
