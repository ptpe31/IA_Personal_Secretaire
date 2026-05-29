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
from app.ui.google_theme import (
    BADGE_RECURRENCE,
    COLUMN_ARCHIVED_BADGE,
    COLUMN_TODO_BADGE,
    COLUMN_URGENT_BADGE,
    EXPANSION_GOOGLE,
    ICON_BTN,
    ICON_BTN_DANGER,
    SUGGESTION_BOX,
    category_badge_classes,
    chip_classes,
    render_date_meta,
    task_card_classes,
)
from app.utils.dates import (
    compute_kanban_column,
    format_date_fr,
    sort_kanban_no_date,
    sort_kanban_todo,
    sort_kanban_urgent,
)
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

    ui.label("Tableau de bord").classes("text-h5 text-weight-medium text-grey-9 q-mb-xs")
    ui.label(
        "Déposez vos scans et gérez vos tâches — tout au même endroit."
    ).classes("text-body2 text-grey-6 q-mb-md")

    refresh_hooks: dict[str, Callable[[], None]] = {"kanban": lambda: None}

    with ui.expansion(
        "Dépôt de documents & Statut",
        icon="cloud_upload",
        value=True,
    ).classes(EXPANSION_GOOGLE).props(
        'header-class="text-weight-medium text-subtitle1 text-grey-9 q-px-md q-py-sm"'
    ) as deposit_expansion:
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
            with ui.row().classes(
                "items-center q-gutter-sm q-mt-sm q-pa-sm bg-blue-1 rounded-borders"
            ):
                ui.spinner("line", size="lg", color="blue-7")
                if job.status == JobStatus.QUEUED:
                    text = f"En attente — {job.filename}"
                else:
                    engine = describe_analysis_engine(queue.client)
                    text = f"Analyse de {job.filename} par {engine} en cours…"
                ui.label(text).classes("text-body2 text-blue-9")

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
                with ui.card().classes(
                    "w-full q-pa-sm bg-red-1 rounded-borders border border-red-2"
                ):
                    with ui.row().classes("items-center q-gutter-sm flex-wrap"):
                        ui.icon("error", color="red-7")
                        ui.label(
                            f"L'analyse IA a échoué pour {failed_count} {doc_label}. "
                            "Vérifiez vos clés API (Paramètres) ou rouvrez l'Inbox."
                        ).classes("text-body2 text-grey-9")

                        def go_inbox_error() -> None:
                            if switch_to_inbox:
                                switch_to_inbox()

                        ui.button(
                            "Voir le détail dans l'Inbox",
                            on_click=go_inbox_error,
                        ).props("flat dense no-caps color=red-7")

            if ready_count > 0:
                doc_label = "document" if ready_count == 1 else "documents"
                verb = "nécessite" if ready_count == 1 else "nécessitent"
                with ui.card().classes(
                    "w-full q-pa-sm bg-amber-1 rounded-borders border border-amber-3"
                ):
                    with ui.row().classes("items-center q-gutter-sm flex-wrap"):
                        ui.icon("warning", color="amber-10")
                        ui.label(
                            f"{ready_count} {doc_label} {verb} votre validation manuelle."
                        ).classes("text-body2 text-grey-9")

                        def go_inbox() -> None:
                            if switch_to_inbox:
                                switch_to_inbox()

                        ui.button(
                            "Aller à l'Inbox",
                            on_click=go_inbox,
                        ).props("flat dense no-caps color=blue-7")

    @ui.refreshable
    def render_category_filters() -> None:
        filter_row.clear()
        with filter_row:
            ui.label("Filtrer").classes("text-subtitle2 text-grey-7 q-mr-sm")
            for key, label in CATEGORY_OPTIONS.items():

                def set_category(k: str = key) -> None:
                    state["category"] = k
                    render_category_filters.refresh()
                    render_board.refresh()

                ui.button(
                    label,
                    on_click=set_category,
                ).props("flat unelevated no-caps").classes(
                    chip_classes(key, state["category"])
                )

    def render_task_card(task: TaskDTO, column: str) -> None:
        cat_label = "Pro" if task.category == "pro" else "Perso"
        urgent = column == "urgent"

        card_classes = task_card_classes(
            document_id=task.document_id,
            created_at=task.created_at,
            urgent=urgent,
        )

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

        with ui.card().classes(card_classes).props("flat"):
            with ui.row().classes("items-start q-gutter-xs q-mb-sm"):
                ui.label(cat_label).classes(category_badge_classes(task.category))
                ui.label(task.title).classes(
                    "text-subtitle2 text-weight-medium text-grey-9 col"
                )
                if task.recurrence_pattern:
                    label = RECURRENCE_DISPLAY.get(task.recurrence_pattern, "Routine")
                    ui.label(f"🔁 {label}").classes(BADGE_RECURRENCE)

            render_date_meta(
                icon="mail",
                label="Reçu le",
                value=format_date_fr(task.date_emission),
            )
            render_date_meta(
                icon="calendar_today",
                label="Événement",
                value=format_date_fr(task.date_event),
            )
            render_date_meta(
                icon="alarm",
                label="Deadline",
                value=format_date_fr(task.deadline),
            )

            if task.suggestion:
                with ui.row().classes(SUGGESTION_BOX + " q-mt-sm items-start q-gutter-sm"):
                    ui.icon("lightbulb", size="sm").classes("text-amber-9")
                    ui.label(task.suggestion).classes("col text-body2")

            with ui.row().classes(
                "items-center q-gutter-sm w-full flex-wrap trankil-card-actions"
            ):
                if column == "archived":

                    def uncheck() -> None:
                        from app.services.task_service import unarchive_task

                        unarchive_task(task.id)
                        render_board.refresh()

                    ui.button("Réouvrir", icon="undo", on_click=uncheck).props(
                        "flat dense round size=sm no-caps"
                    ).classes(ICON_BTN)
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

                    ui.checkbox("Fait", on_change=mark_done).props("color=green-7")

                ui.button(
                    icon="edit",
                    on_click=lambda t=task: open_task_edit_dialog(
                        t,
                        render_board.refresh,
                        on_deleted=render_board.refresh,
                    ),
                ).props("flat round dense size=sm").classes(ICON_BTN).tooltip("Modifier")

                ui.button(
                    icon="delete",
                    on_click=confirm_delete,
                ).props("flat round dense size=sm").classes(ICON_BTN_DANGER).tooltip(
                    "Supprimer"
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

        buckets["urgent"] = sort_kanban_urgent(buckets["urgent"])
        buckets["todo"] = sort_kanban_todo(buckets["todo"])
        buckets["todo_no_date"] = sort_kanban_no_date(buckets["todo_no_date"])

        board_container.clear()
        columns_spec = [
            ("urgent", "EN RETARD / URGENT", COLUMN_URGENT_BADGE),
            ("todo", "À FAIRE", COLUMN_TODO_BADGE),
            ("archived", "ARCHIVÉ", COLUMN_ARCHIVED_BADGE),
        ]

        with board_container:
            for col_key, title, badge_cls in columns_spec:
                if col_key == "todo":
                    count = len(buckets["todo"]) + len(buckets["todo_no_date"])
                else:
                    count = len(buckets[col_key])

                with ui.column().classes(
                    "col bg-white rounded-borders q-pa-md q-gutter-sm"
                ).style(
                    "min-width: 280px; border: 1px solid #e5e7eb;"
                ):
                    with ui.row().classes("items-center q-gutter-sm q-mb-sm"):
                        ui.label(title).classes(
                            "text-subtitle2 text-weight-bold text-grey-8"
                        )
                        ui.label(str(count)).classes(badge_cls)

                    if col_key == "todo":
                        dated = buckets["todo"]
                        undated = buckets["todo_no_date"]
                        if not dated and not undated:
                            ui.label("Aucune tâche").classes("text-grey-5 text-caption")
                        else:
                            for task in dated:
                                render_task_card(task, "todo")
                            if undated:
                                ui.separator().classes("q-my-sm")
                                ui.label("Sans date").classes(
                                    "text-caption text-grey-6 q-mb-xs text-weight-medium"
                                )
                                for task in undated:
                                    render_task_card(task, "todo_no_date")
                    else:
                        items = buckets[col_key]
                        if not items:
                            ui.label("Aucune tâche").classes("text-grey-5 text-caption")
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
