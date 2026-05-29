"""Vue Tableau de bord unifiée — dépôt, statut et Kanban."""

from __future__ import annotations

import logging
from collections.abc import Callable

from nicegui import ui

from app.models.task import TaskDTO
from app.services.inbox_queue import JobStatus, get_inbox_queue
from app.services.analysis_client import describe_analysis_engine
from app.services.task_service import (
    archive_task,
    delete_task,
    list_tasks,
    refresh_task_statuses,
)
from app.ui.calendar_button import add_calendar_sync_button
from app.ui.document_upload import create_document_intake
from app.ui.inbox_ui_safe import run_if_client_alive
from app.ui.manual_task_form import create_manual_task_form
from app.ui.task_edit_dialog import open_task_edit_dialog
from app.ui.tab_registry import register_tab_refresh
from app.utils.dates import compute_kanban_column, format_date_fr
from app.utils.recurrence import RECURRENCE_DISPLAY

logger = logging.getLogger(__name__)

CATEGORY_OPTIONS = {
    "all": "Tout",
    "pro": "Pro uniquement",
    "perso": "Perso uniquement",
}


def create_dashboard_view(*, switch_to_inbox: Callable[[], None] | None = None):
    """Construit la page d'accueil : dépôt en haut, Kanban en bas."""
    queue = get_inbox_queue()
    state = {"category": "all"}

    ui.label("Tableau de bord").classes("text-h5 q-mb-sm")
    ui.label(
        "Déposez vos scans et gérez vos tâches — tout au même endroit."
    ).classes("text-body2 text-grey-7 q-mb-md")

    refresh_hooks: dict[str, Callable[[], None]] = {"kanban": lambda: None}

    with ui.expansion(
        "Dépôt de documents & Statut",
        icon="cloud_upload",
        value=True,
    ).classes("w-full q-mb-md").props(
        'header-class="text-weight-bold text-subtitle1 bg-grey-2 q-px-sm rounded-borders"'
    ).style("border: 1px solid rgba(0,0,0,0.08); border-radius: 4px;") as deposit_expansion:
        with ui.column().classes("w-full q-pa-md q-gutter-sm"):
            create_document_intake(
                triple_column=True,
                compact=True,
                third_column=lambda: create_manual_task_form(
                    on_created=lambda: refresh_hooks["kanban"](),
                ),
            )
            status_container = ui.column().classes("w-full")

    manual_banner_container = ui.column().classes("w-full q-mb-sm")

    ui.separator().classes("q-my-md")

    filter_row = ui.row().classes("w-full items-center q-gutter-sm q-mb-md")
    board_container = ui.row().classes("w-full q-col-gutter-md items-start")

    @ui.refreshable
    def render_processing_status() -> None:
        status_container.clear()
        job = queue.active_processing_job()
        if job is None:
            return
        with status_container:
            with ui.row().classes("items-center q-gutter-sm q-mt-sm"):
                ui.spinner("line", size="lg", color="primary")
                if job.status == JobStatus.QUEUED:
                    text = f"En attente — {job.filename}"
                else:
                    engine = describe_analysis_engine(queue.client)
                    text = f"Analyse de {job.filename} par {engine} en cours…"
                ui.label(text).classes("text-body2")

    @ui.refreshable
    def render_manual_banner() -> None:
        manual_banner_container.clear()
        if queue.active_processing_job() is not None:
            return

        ready_count = queue.manual_pending_count()
        failed_count = queue.failed_analysis_count()
        if ready_count == 0 and failed_count == 0:
            return

        with manual_banner_container:
            if failed_count > 0:
                doc_label = "document" if failed_count == 1 else "documents"
                with ui.card().classes("w-full q-pa-sm bg-red-1"):
                    with ui.row().classes("items-center q-gutter-sm flex-wrap"):
                        ui.icon("error", color="negative")
                        ui.label(
                            f"❌ L'analyse IA a échoué pour {failed_count} {doc_label}. "
                            "Vérifiez vos clés API (Paramètres) ou rouvrez l'Inbox."
                        ).classes("text-body2")

                        def go_inbox_error() -> None:
                            if switch_to_inbox:
                                switch_to_inbox()

                        ui.button(
                            "Voir le détail dans l'Inbox",
                            on_click=go_inbox_error,
                        ).props("flat dense color=negative no-caps")

            if ready_count > 0:
                doc_label = "document" if ready_count == 1 else "documents"
                verb = "nécessite" if ready_count == 1 else "nécessitent"
                with ui.card().classes("w-full q-pa-sm bg-orange-1"):
                    with ui.row().classes("items-center q-gutter-sm flex-wrap"):
                        ui.icon("warning", color="orange-10")
                        ui.label(
                            f"⚠️ {ready_count} {doc_label} {verb} votre validation manuelle."
                        ).classes("text-body2")

                        def go_inbox() -> None:
                            if switch_to_inbox:
                                switch_to_inbox()

                        ui.button(
                            "Cliquez ici pour aller à l'Inbox",
                            on_click=go_inbox,
                        ).props("flat dense color=primary no-caps")

    @ui.refreshable
    def render_category_filters() -> None:
        filter_row.clear()
        with filter_row:
            ui.label("Filtrer :").classes("text-subtitle2")
            for key, label in CATEGORY_OPTIONS.items():

                def set_category(k: str = key) -> None:
                    state["category"] = k
                    render_category_filters.refresh()
                    render_board.refresh()

                ui.button(
                    label,
                    on_click=set_category,
                ).props(
                    "dense"
                    + (" color=primary unelevated" if state["category"] == key else " outline")
                )

    def render_task_card(task: TaskDTO, column: str) -> None:
        cat_label = "Pro" if task.category == "pro" else "Perso"
        cat_color = "blue-8" if task.category == "pro" else "green-8"
        urgent = column == "urgent"

        card_classes = "w-full q-mb-sm q-pl-md q-pr-sm q-py-sm"
        if urgent:
            card_classes += " bg-red-1 border-left-4 border-red q-pl-lg"

        def confirm_delete(t: TaskDTO = task) -> None:
            with ui.dialog() as dialog, ui.card().classes("q-pa-md"):
                ui.label("Supprimer cette tâche ?").classes("text-subtitle1 q-mb-xs")
                ui.label(t.title).classes("text-body2 q-mb-sm")
                ui.label(
                    "Suppression définitive de la base. Le fichier GED n'est pas effacé."
                ).classes("text-caption text-grey-7 q-mb-md")
                with ui.row().classes("justify-end q-gutter-sm w-full"):
                    ui.button("Annuler", on_click=dialog.close).props("flat")

                    def do_delete(tid: int = t.id) -> None:
                        delete_task(tid)
                        dialog.close()
                        ui.notify("Tâche supprimée.", type="positive")
                        render_board.refresh()

                    ui.button(
                        "Supprimer",
                        icon="delete",
                        on_click=do_delete,
                    ).props("color=negative unelevated")

            dialog.open()

        with ui.card().classes(card_classes):
            with ui.row().classes("items-center q-gutter-xs q-mb-xs"):
                ui.badge(cat_label).props(f"color={cat_color}")
                ui.label(task.title).classes("text-subtitle2 col")
                if task.recurrence_pattern:
                    label = RECURRENCE_DISPLAY.get(task.recurrence_pattern, "Routine")
                    ui.badge(f"🔁 {label}").props("color=purple-4").classes("text-caption")

            ui.label(f"• Reçu le : {format_date_fr(task.date_emission)}").classes(
                "text-caption"
            )
            ui.label(f"• Date événement : {format_date_fr(task.date_event)}").classes(
                "text-caption"
            )
            ui.label(f"• Deadline : {format_date_fr(task.deadline)}").classes(
                "text-caption"
            )

            if task.suggestion:
                ui.label(f"💡 {task.suggestion}").classes(
                    "text-caption text-amber-10 italic q-mt-xs"
                ).style("color: #b45309;")

            with ui.row().classes("items-center q-gutter-xs q-mt-xs w-full flex-wrap"):
                if column == "archived":

                    def uncheck() -> None:
                        from app.services.task_service import unarchive_task

                        unarchive_task(task.id)
                        render_board.refresh()

                    ui.button("Réouvrir", icon="undo", on_click=uncheck).props(
                        "dense flat size=sm"
                    )
                else:

                    def mark_done(e, tid: int = task.id) -> None:
                        if e.value:
                            spawned_id = archive_task(tid)
                            if spawned_id:
                                ui.notify(
                                    "Tâche archivée — prochaine occurrence planifiée.",
                                    type="positive",
                                )
                            else:
                                ui.notify("Tâche archivée.", type="positive")
                            render_board.refresh()

                    ui.checkbox("Fait", on_change=mark_done)

                ui.button(
                    icon="edit",
                    on_click=lambda t=task: open_task_edit_dialog(
                        t,
                        render_board.refresh,
                        on_deleted=render_board.refresh,
                    ),
                ).props("dense flat round size=sm color=primary").tooltip("Modifier")

                ui.button(
                    "Suppr.",
                    icon="delete",
                    on_click=confirm_delete,
                ).props("dense size=sm color=negative outline").tooltip(
                    "Supprimer de la base"
                )

                if column != "archived":
                    add_calendar_sync_button(task, on_synced=render_board.refresh)

    @ui.refreshable
    def render_board() -> None:
        refresh_task_statuses()
        tasks = list_tasks(category_filter=state["category"])

        buckets: dict[str, list[TaskDTO]] = {
            "urgent": [],
            "todo": [],
            "todo_no_date": [],
            "archived": [],
        }
        for task in tasks:
            col = compute_kanban_column(
                completed_at=task.completed_at,
                deadline=task.deadline,
            )
            buckets[col].append(task)

        board_container.clear()
        columns_spec = [
            ("urgent", "EN RETARD / URGENT", "red"),
            ("todo", "À FAIRE", "primary"),
            ("archived", "ARCHIVÉ", "green"),
        ]

        with board_container:
            for col_key, title, color in columns_spec:
                with ui.column().classes("col q-pl-xs").style("min-width: 280px"):
                    ui.label(title).classes(f"text-subtitle1 text-{color} q-mb-sm")

                    if col_key == "todo":
                        dated = buckets["todo"]
                        undated = buckets["todo_no_date"]
                        if not dated and not undated:
                            ui.label("Aucune tâche").classes("text-grey-6 text-caption")
                        else:
                            for task in dated:
                                render_task_card(task, "todo")
                            if undated:
                                ui.separator().classes("q-my-sm")
                                ui.label("Sans date").classes(
                                    "text-caption text-grey-7 q-mb-xs"
                                )
                                for task in undated:
                                    render_task_card(task, "todo_no_date")
                    else:
                        items = buckets[col_key]
                        if not items:
                            ui.label("Aucune tâche").classes("text-grey-6 text-caption")
                        else:
                            for task in items:
                                render_task_card(task, col_key)

    def refresh_dashboard() -> None:
        refresh_task_statuses()
        render_processing_status.refresh()
        render_manual_banner.refresh()
        render_category_filters.refresh()
        render_board.refresh()

    def _detach_queue_listener() -> None:
        queue.remove_listener(on_queue_changed)

    def on_queue_changed() -> None:
        def _refresh_from_queue() -> None:
            processing = queue.active_processing_job()
            if processing:
                deposit_expansion.value = True
            elif queue.manual_pending_count() == 0 and queue.failed_analysis_count() == 0:
                deposit_expansion.value = False
            render_processing_status.refresh()
            render_manual_banner.refresh()
            render_board.refresh()

        try:
            run_if_client_alive(
                status_container,
                _refresh_from_queue,
                on_dead=_detach_queue_listener,
            )
        except RuntimeError:
            _detach_queue_listener()

    queue.add_listener(on_queue_changed)
    try:
        status_container.client.on_disconnect(_detach_queue_listener)
    except RuntimeError:
        logger.debug("Impossible d'enregistrer on_disconnect sur le Dashboard.")

    refresh_hooks["kanban"] = render_board.refresh

    render_processing_status()
    render_manual_banner()
    render_category_filters()
    render_board()

    register_tab_refresh("dashboard", refresh_dashboard)
    ui.timer(60.0, render_board.refresh)
    return refresh_dashboard
