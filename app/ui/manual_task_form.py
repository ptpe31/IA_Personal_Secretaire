"""Formulaire de création manuelle / routine — Dashboard."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from nicegui import ui

from app.services.task_service import create_manual_task
from app.utils.recurrence import RECURRENCE_SELECT_OPTIONS, pattern_from_label


def create_manual_task_form(*, on_created: Callable[[], None]) -> None:
    """Carte compacte « Création manuelle / Routine » pour le Dashboard."""
    with ui.card().classes("w-full full-height q-pa-md").props("flat bordered"):
        ui.label("Création manuelle / Routine").classes("text-subtitle2 q-mb-sm")

        title_input = ui.input(
            "Titre / Action",
            placeholder="Titre de la tâche",
        ).props("dense outlined").classes("w-full")

        ui.label("Catégorie").classes("text-caption text-grey-7 q-mt-xs")
        category_input = ui.radio(
            {"pro": "Pro", "perso": "Perso"},
            value="pro",
        ).props("inline dense")

        start_date_input = ui.input(
            "Date de départ / Première échéance",
            value=date.today().isoformat(),
        ).props("type=date dense outlined").classes("w-full")

        recurrence_select = ui.select(
            RECURRENCE_SELECT_OPTIONS,
            value="Aucune",
            label="Récurrence",
        ).props("dense outlined").classes("w-full")

        suggestion_input = ui.input(
            "Suggestion / Note",
            placeholder="Optionnel",
        ).props("dense outlined").classes("w-full")

        def submit() -> None:
            title = (title_input.value or "").strip()
            if not title:
                ui.notify("Le titre est obligatoire.", type="negative")
                return
            if not start_date_input.value:
                ui.notify("La date de départ est obligatoire.", type="negative")
                return

            try:
                start = date.fromisoformat(str(start_date_input.value))
            except ValueError:
                ui.notify("Date invalide.", type="negative")
                return

            pattern = pattern_from_label(str(recurrence_select.value or "Aucune"))

            try:
                create_manual_task(
                    title=title,
                    category=str(category_input.value or "pro"),
                    start_date=start,
                    recurrence_pattern=pattern,
                    suggestion=(suggestion_input.value or "").strip() or None,
                )
            except Exception as exc:
                ui.notify(f"Erreur : {exc}", type="negative")
                return

            ui.notify("Tâche créée.", type="positive")
            title_input.value = ""
            suggestion_input.value = ""
            recurrence_select.value = "Aucune"
            on_created()

        ui.button(
            "Créer la tâche",
            icon="add",
            on_click=submit,
        ).props("color=primary unelevated").classes("w-full q-mt-sm")
