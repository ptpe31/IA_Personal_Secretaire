"""Vue Tableau de bord unifiée — dépôt, statut et Kanban."""

from __future__ import annotations

import logging
from collections.abc import Callable

from nicegui import ui

from app import config
from app.models.task import TaskDTO
from app.services.inbox_queue import JobStatus, get_inbox_queue
from app.services.analysis_client import describe_analysis_engine
from app.services.task_service import (
    archive_task,
    delete_task,
    delete_tasks,
    list_all_tags,
    list_tasks,
    matches_task_search,
    refresh_task_statuses,
    suggest_tags,
)
from app.ui.calendar_button import add_calendar_sync_button
from app.ui.document_upload import create_document_intake
from app.ui.inbox_ui_safe import run_if_client_alive
from app.ui.manual_task_form import create_manual_task_form
from app.ui.task_edit_dialog import open_task_edit_dialog
from app.ui.task_badges import (
    notify_task_completed,
    render_frequence_icon,
    render_source_url_link,
)
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
    batch_border_left_classes,
    category_badge_classes,
    chip_classes,
    render_date_meta,
    task_card_classes,
    view_toggle_classes,
)
from app.utils.dates import (
    compute_kanban_column,
    format_date_fr,
    kanban_batch_sort_key,
    sort_kanban_no_date,
    sort_kanban_todo,
    sort_kanban_urgent,
    sort_list_view_tasks,
)
from app.utils.finder import open_file
from app.utils.recurrence import RECURRENCE_DISPLAY

logger = logging.getLogger(__name__)

LIST_GRID = "grid grid-cols-12 gap-x-4 w-full items-center"
LIST_COL_TITLE = "col-span-6 flex items-center gap-2 min-w-0"
LIST_COL_DEADLINE = "col-span-2 flex items-center gap-2 min-w-0"
LIST_COL_EVENT = "col-span-2 flex items-center gap-2 min-w-0"
LIST_COL_SUGGESTION = "col-span-1 flex items-center gap-2 min-w-0 overflow-hidden"
LIST_COL_ACTIONS = "col-span-1 flex items-center justify-end gap-0.5 shrink-0"
LIST_DATE_TEXT = "text-xs text-gray-400 whitespace-nowrap"
LIST_ICON_MUTED = "text-gray-400 shrink-0"

CATEGORY_OPTIONS = {
    "all": "Tout",
    "pro": "Pro uniquement",
    "perso": "Perso uniquement",
}


def create_dashboard_view(*, switch_to_inbox: Callable[[], None] | None = None):
    """Construit la page d'accueil : dépôt en haut, Kanban en bas."""
    queue = get_inbox_queue()
    state = {"category": "all", "search": ""}

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

    ui.separator().classes("q-my-sm")

    search_filter_container = ui.column().classes("w-full q-mb-xs")
    tag_suggestions_row = ui.row().classes(
        "w-full q-gutter-xs q-pl-md q-mb-xs flex-wrap items-center"
    )
    tasks_workspace_container = ui.column().classes("w-full")

    with search_filter_container:
        with ui.row().classes("w-full items-center q-gutter-sm flex-wrap"):
            with ui.row().classes(
                "col-grow items-center q-gutter-xs trankil-omnibox-wrap"
            ).style("min-width: 220px"):
                ui.icon("search", size="sm").classes("text-grey-6 shrink-0")
                search_input = ui.input(
                    placeholder="Rechercher une tâche ou un tag…",
                ).props("dense borderless clearable").classes("col-grow").style(
                    "min-width: 0"
                )
            category_filter_row = ui.row().classes(
                "items-center q-gutter-sm shrink-0"
            )

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

    def on_search_change(_=None) -> None:
        state["search"] = (search_input.value or "").strip()
        render_tag_suggestions.refresh()
        render_tasks_workspace.refresh()

    search_input.on("update:model-value", on_search_change)

    @ui.refreshable
    def render_category_filters() -> None:
        category_filter_row.clear()
        with category_filter_row:
            ui.label("Filtrer").classes("text-subtitle2 text-grey-7 q-mr-xs")
            for key, label in CATEGORY_OPTIONS.items():

                def set_category(k: str = key) -> None:
                    state["category"] = k
                    render_category_filters.refresh()
                    render_tasks_workspace.refresh()

                ui.button(
                    label,
                    on_click=set_category,
                ).props("flat unelevated no-caps").classes(
                    chip_classes(key, state["category"])
                )

    @ui.refreshable
    def render_tag_suggestions() -> None:
        tag_suggestions_row.clear()
        query = state["search"]
        if "#" not in query:
            return

        hash_idx = query.rfind("#")
        prefix = query[hash_idx + 1 :]
        matches = suggest_tags(prefix, list_all_tags())
        if not matches:
            return

        with tag_suggestions_row:
            for tag in matches:

                def select_tag(t: str = tag) -> None:
                    state["search"] = f"#{t}"
                    search_input.value = state["search"]
                    render_tag_suggestions.refresh()
                    render_tasks_workspace.refresh()

                ui.button(f"#{tag}", on_click=select_tag).props(
                    "flat unelevated no-caps"
                ).classes("trankil-tag-suggestion")

    def confirm_delete_task(task: TaskDTO) -> None:
        with ui.dialog() as dialog, ui.card().classes("q-pa-md"):
            ui.label("Supprimer cette tâche ?").classes("text-subtitle1 q-mb-xs")
            ui.label(task.title).classes("text-body2 q-mb-sm")
            ui.label(
                "Suppression définitive de la base. Le fichier GED n'est pas effacé."
            ).classes("text-caption text-grey-7 q-mb-md")
            with ui.row().classes("justify-end q-gutter-sm w-full"):
                ui.button("Annuler", on_click=dialog.close).props("flat")

                def do_delete(tid: int = task.id) -> None:
                    delete_task(tid)
                    dialog.close()
                    ui.notify("Tâche supprimée.", type="positive")
                    render_tasks_workspace.refresh()

                ui.button(
                    "Supprimer",
                    icon="delete",
                    on_click=do_delete,
                ).props("color=negative unelevated")

        dialog.open()

    def confirm_delete_batch(batch: list[TaskDTO]) -> None:
        count = len(batch)
        if count == 0:
            return
        parent_title = batch[0].title
        with ui.dialog() as dialog, ui.card().classes("q-pa-md"):
            ui.label("Supprimer tout le lot ?").classes("text-subtitle1 q-mb-xs")
            if count == 1:
                ui.label(parent_title).classes("text-body2 q-mb-sm")
            else:
                ui.label(parent_title).classes("text-body2 text-weight-medium q-mb-xs")
                ui.label(
                    f"Et {count - 1} autre(s) tâche(s) liée(s) au même document."
                ).classes("text-body2 q-mb-sm")
            ui.label(
                "Suppression définitive de la base. Le fichier GED n'est pas effacé."
            ).classes("text-caption text-grey-7 q-mb-md")
            with ui.row().classes("justify-end q-gutter-sm w-full"):
                ui.button("Annuler", on_click=dialog.close).props("flat")

                def do_delete(b: list[TaskDTO] = batch) -> None:
                    deleted = delete_tasks([t.id for t in b])
                    dialog.close()
                    ui.notify(
                        f"{deleted} tâche(s) supprimée(s).",
                        type="positive",
                    )
                    render_tasks_workspace.refresh()

                ui.button(
                    f"Supprimer le lot ({count})",
                    icon="delete_sweep",
                    on_click=do_delete,
                ).props("color=negative unelevated")

        dialog.open()

    def render_task_card(task: TaskDTO, column: str) -> None:
        cat_label = "Pro" if task.category == "pro" else "Perso"
        urgent = column == "urgent"

        card_classes = task_card_classes(
            document_id=task.document_id,
            created_at=task.created_at,
            urgent=urgent,
        )

        def confirm_delete(t: TaskDTO = task) -> None:
            confirm_delete_task(t)

        with ui.card().classes(card_classes).props("flat"):
            with ui.row().classes("items-start q-gutter-xs q-mb-sm"):
                ui.label(cat_label).classes(category_badge_classes(task.category))
                render_frequence_icon(task)
                ui.label(task.title).classes(
                    "text-subtitle2 text-weight-medium text-grey-9 col"
                )
                if task.recurrence_pattern:
                    label = RECURRENCE_DISPLAY.get(task.recurrence_pattern, "Routine")
                    ui.label(f"🔁 {label}").classes(BADGE_RECURRENCE)
                render_source_url_link(task)

            render_date_meta(
                icon="mail",
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
                        render_tasks_workspace.refresh()

                    ui.button("Réouvrir", icon="undo", on_click=uncheck).props(
                        "flat dense round size=sm no-caps"
                    ).classes(ICON_BTN)
                else:

                    def mark_done(e, tid: int = task.id) -> None:
                        if e.value:
                            result = archive_task(tid)
                            notify_task_completed(tid, result)
                            render_tasks_workspace.refresh()

                    ui.checkbox("Fait", on_change=mark_done).props("color=green-7")

                ui.button(
                    icon="edit",
                    on_click=lambda t=task: open_task_edit_dialog(
                        t,
                        render_tasks_workspace.refresh,
                        on_deleted=render_tasks_workspace.refresh,
                    ),
                ).props("flat round dense size=sm").classes(ICON_BTN).tooltip("Modifier")

                if task.stored_path:

                    def open_ged_document(t: TaskDTO = task) -> None:
                        path = config.ROOT_PATH / t.stored_path
                        try:
                            open_file(path)
                        except Exception as exc:
                            ui.notify(str(exc), type="negative")

                    ui.button(
                        icon="alternate_email",
                        on_click=open_ged_document,
                    ).props("flat round dense size=sm").classes(ICON_BTN).tooltip(
                        "Ouvrir le document GED"
                    )

                ui.button(
                    icon="delete",
                    on_click=confirm_delete,
                ).props("flat round dense size=sm").classes(ICON_BTN_DANGER).tooltip(
                    "Supprimer"
                )

                if column != "archived":
                    add_calendar_sync_button(task, on_synced=render_tasks_workspace.refresh)

    def _group_tasks_into_batches(tasks: list[TaskDTO]) -> list[list[TaskDTO]]:
        batches: list[list[TaskDTO]] = []
        current_key: tuple | None = None
        current_batch: list[TaskDTO] = []
        for task in tasks:
            key = kanban_batch_sort_key(task)
            if key != current_key:
                if current_batch:
                    batches.append(current_batch)
                current_batch = [task]
                current_key = key
            else:
                current_batch.append(task)
        if current_batch:
            batches.append(current_batch)
        return batches

    def render_list_grid_row(
        task: TaskDTO,
        *,
        is_child: bool,
        batch: list[TaskDTO] | None = None,
    ) -> None:
        cat_label = "Pro" if task.category == "pro" else "Perso"
        title_classes = (
            "font-normal text-gray-500 text-sm truncate min-w-0 "
            "cursor-pointer hover:underline hover:text-gray-700"
            if is_child
            else "font-semibold text-gray-900 truncate min-w-0 "
            "cursor-pointer hover:underline hover:text-blue-700"
        )
        title_col = LIST_COL_TITLE + (" pl-4" if is_child else "")
        row_classes = "trankil-list-row px-4 hover:bg-gray-50/60"
        if is_child:
            row_classes += " py-2 border-t border-gray-100 bg-gray-50/50"
        else:
            row_classes += " py-3 bg-white"

        with ui.element("div").classes(f"{LIST_GRID} {row_classes}"):
            with ui.element("div").classes(title_col):
                if not is_child and task.stored_path:

                    def open_ged_document(t: TaskDTO = task) -> None:
                        path = config.ROOT_PATH / t.stored_path
                        try:
                            open_file(path)
                        except Exception as exc:
                            ui.notify(str(exc), type="negative")

                    ui.button(
                        icon="alternate_email",
                        on_click=open_ged_document,
                    ).props("flat round dense size=sm").classes(
                        ICON_BTN + " shrink-0"
                    ).tooltip("Ouvrir le document GED")
                if is_child:
                    ui.icon("subdirectory_arrow_right").classes(
                        "text-gray-300 text-base shrink-0"
                    )
                ui.label(cat_label).classes(
                    f"{category_badge_classes(task.category)} shrink-0"
                )
                render_frequence_icon(task)
                title_label = ui.label(task.title).classes(title_classes)
                title_label.on(
                    "click",
                    lambda t=task: open_task_edit_dialog(
                        t,
                        render_tasks_workspace.refresh,
                        on_deleted=render_tasks_workspace.refresh,
                    ),
                ).tooltip("Modifier")
                render_source_url_link(task)

            with ui.element("div").classes(LIST_COL_DEADLINE):
                with ui.row().classes("items-center gap-2 min-w-0"):
                    ui.icon("alarm", size="xs").classes(LIST_ICON_MUTED)
                    ui.label(format_date_fr(task.deadline)).classes(LIST_DATE_TEXT)

            with ui.element("div").classes(LIST_COL_EVENT):
                with ui.row().classes("items-center gap-2 min-w-0"):
                    ui.icon("calendar_today", size="xs").classes(LIST_ICON_MUTED)
                    ui.label(format_date_fr(task.date_event)).classes(LIST_DATE_TEXT)

            with ui.element("div").classes(LIST_COL_SUGGESTION):
                if task.suggestion:
                    with ui.row().classes("items-center gap-2 min-w-0 overflow-hidden"):
                        ui.icon("lightbulb", size="xs").classes(
                            "text-amber-7 shrink-0"
                        )
                        suggestion_label = ui.label(task.suggestion).classes(
                            f"{LIST_DATE_TEXT} truncate min-w-0"
                        )
                        suggestion_label.tooltip(task.suggestion)
                else:
                    ui.label("—").classes(LIST_DATE_TEXT)

            with ui.element("div").classes(LIST_COL_ACTIONS):

                def mark_done(e, tid: int = task.id) -> None:
                    if e.value:
                        result = archive_task(tid)
                        notify_task_completed(tid, result)
                        render_tasks_workspace.refresh()

                ui.checkbox(on_change=mark_done).props("color=green-7 dense").tooltip(
                    "Fait"
                )
                if not is_child and batch and len(batch) > 1:
                    ui.button(
                        icon="delete_sweep",
                        on_click=lambda b=batch: confirm_delete_batch(b),
                    ).props("flat round dense size=sm").classes(
                        ICON_BTN_DANGER
                    ).tooltip("Supprimer tout le lot")
                ui.button(
                    icon="delete",
                    on_click=lambda t=task: confirm_delete_task(t),
                ).props("flat round dense size=sm").classes(ICON_BTN_DANGER).tooltip(
                    "Supprimer"
                )

    def render_list_batch_block(batch: list[TaskDTO]) -> None:
        if not batch:
            return
        parent = batch[0]
        children = batch[1:]
        border_cls = batch_border_left_classes(parent.document_id, parent.created_at)

        with ui.column().classes(
            f"trankil-list-batch w-full bg-white rounded-xl border "
            f"border-gray-200 mb-6 overflow-hidden {border_cls}"
        ):
            render_list_grid_row(parent, is_child=False, batch=batch)
            for child in children:
                render_list_grid_row(child, is_child=True)

    def render_list_header() -> None:
        with ui.element("div").classes(
            f"{LIST_GRID} px-4 py-3 bg-white rounded-t-xl border border-gray-200 "
            "border-b-0 text-xs font-medium text-gray-500 uppercase tracking-wide"
        ):
            ui.label("Tâche").classes(LIST_COL_TITLE)
            ui.label("Deadline").classes(LIST_COL_DEADLINE)
            ui.label("Événement").classes(LIST_COL_EVENT)
            ui.label("Conseil IA").classes(LIST_COL_SUGGESTION)
            ui.label("").classes(LIST_COL_ACTIONS)

    def render_list_view(buckets: dict[str, list[TaskDTO]]) -> None:
        active_tasks = (
            buckets["urgent"] + buckets["todo"] + buckets["todo_no_date"]
        )
        sorted_tasks = sort_list_view_tasks(active_tasks)
        batches = _group_tasks_into_batches(sorted_tasks)

        if not batches:
            with ui.column().classes(
                "w-full bg-white rounded-xl border border-gray-200 p-6"
            ):
                ui.label("Aucune tâche active").classes("text-grey-5 text-caption")
            return

        render_list_header()
        with ui.column().classes("w-full"):
            for batch in batches:
                render_list_batch_block(batch)

    def _load_task_buckets() -> dict[str, list[TaskDTO]]:
        refresh_task_statuses()
        tasks = list_tasks(category_filter=state["category"])
        search_q = state["search"]
        if search_q:
            tasks = [t for t in tasks if matches_task_search(search_q, t)]
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
        return buckets

    def render_kanban_board(buckets: dict[str, list[TaskDTO]]) -> None:
        board_container = ui.row().classes("w-full q-col-gutter-md items-start")
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

    @ui.refreshable
    def render_tasks_workspace() -> None:
        vue_mode, set_vue_mode = ui.state("kanban")
        buckets = _load_task_buckets()

        tasks_workspace_container.clear()
        with tasks_workspace_container:
            with ui.row().classes("w-full items-center q-gutter-xs q-mb-sm"):
                ui.label("Vue").classes("text-subtitle2 text-grey-7 q-mr-sm")
                ui.button(
                    icon="view_kanban",
                    on_click=lambda: set_vue_mode("kanban"),
                ).props("flat unelevated round dense").classes(
                    view_toggle_classes(vue_mode == "kanban")
                ).tooltip("Kanban")
                ui.button(
                    icon="list",
                    on_click=lambda: set_vue_mode("liste"),
                ).props("flat unelevated round dense").classes(
                    view_toggle_classes(vue_mode == "liste")
                ).tooltip("Liste")

            if vue_mode == "liste":
                render_list_view(buckets)
            else:
                render_kanban_board(buckets)

    def refresh_dashboard() -> None:
        refresh_task_statuses()
        render_processing_status.refresh()
        render_manual_banner.refresh()
        render_category_filters.refresh()
        render_tag_suggestions.refresh()
        render_tasks_workspace.refresh()

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
            render_tasks_workspace.refresh()

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

    refresh_hooks["kanban"] = render_tasks_workspace.refresh

    render_processing_status()
    render_manual_banner()
    render_category_filters()
    render_tag_suggestions()
    render_tasks_workspace()

    register_tab_refresh("dashboard", refresh_dashboard)
    ui.timer(60.0, render_tasks_workspace.refresh)
    return refresh_dashboard
