"""Dialogue d'édition de tâche — spec §6.3."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from nicegui import ui

from app.models.task import TaskDTO
from app.services.task_service import parse_tags_input, update_task
from app.utils.dates import parse_optional_date


def open_task_edit_dialog(task: TaskDTO, on_saved: Callable[[], None]) -> None:
    """Ouvre un modal NiceGUI pour modifier une tâche."""
    with ui.dialog() as dialog, ui.card().classes("w-full").style("min-width: 420px"):
        ui.label("Modifier la tâche").classes("text-h6 q-mb-md")

        title_input = ui.input("Titre / Action", value=task.title).classes("w-full")

        with ui.row().classes("w-full q-col-gutter-sm"):
            date_emission_input = ui.input(
                "Date d'émission",
                value=task.date_emission.isoformat(),
            ).props("type=date").classes("col")
            date_event_input = ui.input(
                "Date événement",
                value=task.date_event.isoformat() if task.date_event else "",
            ).props("type=date").classes("col")

        deadline_input = ui.input(
            "Deadline",
            value=task.deadline.isoformat() if task.deadline else "",
        ).props("type=date").classes("w-full")

        ui.label("Catégorie").classes("text-caption text-grey-7")
        category_input = ui.radio(
            {"pro": "Pro", "perso": "Perso"},
            value=task.category,
        ).props("inline")

        tags_input = ui.input(
            "Tags (séparés par des virgules)",
            value=", ".join(task.tags),
        ).classes("w-full")

        notes_input = ui.textarea(
            "Notes",
            value=task.notes or "",
        ).props("outlined autogrow").classes("w-full")

        with ui.row().classes("w-full justify-end q-gutter-sm q-mt-md"):
            ui.button("Annuler", on_click=dialog.close).props("flat")

            def save() -> None:
                try:
                    update_task(
                        task.id,
                        title=title_input.value or task.title,
                        date_emission=date.fromisoformat(date_emission_input.value),
                        date_event=parse_optional_date(date_event_input.value),
                        deadline=parse_optional_date(deadline_input.value),
                        category=str(category_input.value),
                        tags=parse_tags_input(tags_input.value or ""),
                        notes=notes_input.value,
                    )
                    ui.notify("Tâche mise à jour.", type="positive")
                    dialog.close()
                    on_saved()
                except Exception as exc:
                    ui.notify(f"Erreur : {exc}", type="negative")

            ui.button("Enregistrer", icon="save", on_click=save).props(
                "color=primary unelevated"
            )

    dialog.open()
