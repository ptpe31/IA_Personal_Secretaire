"""Vue Tableau de bord Kanban — spec §6."""

from __future__ import annotations

from nicegui import ui

from app.models.task import TaskDTO
from app.services.task_service import archive_task, list_all_tags, list_tasks, refresh_task_statuses
from app.ui.task_edit_dialog import open_task_edit_dialog
from app.utils.dates import compute_kanban_column, format_date_fr

CATEGORY_OPTIONS = {
    "all": "Tout",
    "pro": "Pro uniquement",
    "perso": "Perso uniquement",
}


def create_dashboard_view() -> None:
    """Construit le Kanban 3 colonnes avec filtres."""
    state = {"category": "all", "tags": set()}

    ui.label("Tableau de bord").classes("text-h5 q-mb-sm")
    ui.label("Gérez vos tâches par priorité et catégorie.").classes(
        "text-body2 text-grey-7 q-mb-md"
    )

    filter_row = ui.row().classes("w-full items-center q-gutter-sm q-mb-md")
    tag_chip_container = ui.row().classes("w-full q-gutter-xs q-mb-md flex-wrap")
    board_container = ui.row().classes("w-full q-col-gutter-md items-start")

    @ui.refreshable
    def render_tag_filters() -> None:
        tag_chip_container.clear()
        all_tags = list_all_tags()
        with tag_chip_container:
            if not all_tags:
                ui.label("Aucun tag — validez un document dans l'Inbox.").classes(
                    "text-caption text-grey-6"
                )
                return
            for tag in all_tags:
                selected = tag.lower() in state["tags"]

                def toggle(t: str = tag) -> None:
                    key = t.lower()
                    if key in state["tags"]:
                        state["tags"].remove(key)
                    else:
                        state["tags"].add(key)
                    render_tag_filters.refresh()
                    render_board.refresh()

                btn = ui.button(f"#{tag}", on_click=toggle).props(
                    "dense rounded" + (" color=primary" if selected else " outline")
                )

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

        card_classes = "w-full q-pa-sm q-mb-sm"
        if urgent:
            card_classes += " bg-red-1 border-left-4 border-red"

        with ui.card().classes(card_classes).tight():
            with ui.row().classes("items-center q-gutter-xs"):
                ui.badge(cat_label).props(f"color={cat_color}")
                ui.label(task.title).classes("text-subtitle2 col")

            ui.label(f"• Reçu le : {format_date_fr(task.date_emission)}").classes(
                "text-caption"
            )
            ui.label(f"• Deadline : {format_date_fr(task.deadline)}").classes(
                "text-caption"
            )

            if task.tags:
                ui.label("• Tags : " + " ".join(f"#{t}" for t in task.tags)).classes(
                    "text-caption text-grey-8"
                )

            with ui.row().classes("items-center q-gutter-sm q-mt-xs"):
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
                            archive_task(tid)
                            ui.notify("Tâche archivée.", type="positive")
                            render_board.refresh()

                    ui.checkbox("Fait", on_change=mark_done)

                ui.button(
                    icon="edit",
                    on_click=lambda t=task: open_task_edit_dialog(t, render_board.refresh),
                ).props("dense flat round size=sm").tooltip("Modifier")

    @ui.refreshable
    def render_board() -> None:
        refresh_task_statuses()
        tag_filter_list = list(state["tags"]) if state["tags"] else None
        tasks = list_tasks(
            category_filter=state["category"],
            tag_filters=tag_filter_list,
        )

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
                with ui.column().classes("col").style("min-width: 280px"):
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

    render_category_filters()
    render_tag_filters()
    render_board()

    ui.timer(60.0, render_board.refresh)
