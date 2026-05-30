"""Vue GED / Archives — spec §7."""

from __future__ import annotations

from nicegui import ui

from app.models.archive import ArchiveItem
from app.services.archive_service import search_archives
from app.services.task_service import list_all_tags, suggest_tags
from app.ui.google_theme import chip_classes
from app.ui.tab_registry import register_tab_refresh
from app.utils.dates import format_date_fr, parse_optional_date
from app.utils.file_preview import preview_data_url
from app.utils.finder import open_file, reveal_in_finder

CATEGORY_OPTIONS = {
    "all": "Tout",
    "pro": "Pro",
    "perso": "Perso",
}


def create_ged_view():
    """Construit la vue Archives avec recherche et preview."""
    state = {
        "category": "all",
        "search": "",
        "selected": None,
        "sort_desc": True,
    }

    ui.label("Archives GED").classes("text-h5 q-mb-xs")
    ui.label("Recherchez vos documents par mot-clé, tag ou date.").classes(
        "text-body2 text-grey-7 q-mb-sm"
    )

    search_filter_container = ui.column().classes("w-full q-mb-xs")
    tag_suggestions_row = ui.row().classes(
        "w-full q-gutter-xs q-pl-md q-mb-xs flex-wrap items-center"
    )

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
            sort_toggle = ui.button(icon="arrow_downward").props(
                "flat round dense"
            ).classes("trankil-view-toggle shrink-0").tooltip("Tri par date d'émission")
            category_filter_row = ui.row().classes(
                "items-center q-gutter-sm shrink-0"
            )

    with ui.row().classes("w-full q-col-gutter-sm q-mb-sm items-end"):
        date_from_input = ui.input("Du").props("type=date outlined dense").classes("col")
        date_to_input = ui.input("Au").props("type=date outlined dense").classes("col")

    results_label = ui.label("").classes("text-caption text-grey-7 q-mb-sm")

    with ui.row().classes("w-full q-col-gutter-md no-wrap"):
        results_container = ui.column().classes("col").style(
            "min-width: 38%; max-width: 42%; max-height: 70vh; overflow-y: auto;"
        )
        preview_container = ui.column().classes("col-grow").style("min-width: 55%")

    def refresh_search_results() -> None:
        state["search"] = (search_input.value or "").strip()
        render_tag_suggestions.refresh()
        render_results.refresh()

    def on_search_change(_=None) -> None:
        refresh_search_results()

    search_input.on("update:model-value", on_search_change)
    date_from_input.on("update:model-value", refresh_search_results)
    date_to_input.on("update:model-value", refresh_search_results)

    def show_preview(item: ArchiveItem) -> None:
        state["selected"] = item
        preview_container.clear()
        with preview_container:
            ui.label(item.title).classes("text-h6 q-mb-xs")
            with ui.row().classes("items-center q-gutter-xs q-mb-sm"):
                cat = "Pro" if item.category == "pro" else "Perso"
                ui.badge(cat).props(
                    f"color={'blue-8' if item.category == 'pro' else 'green-8'}"
                )
                ui.label(f"Émission : {format_date_fr(item.date_emission)}").classes(
                    "text-caption"
                )

            if not item.file_exists:
                ui.label("Fichier introuvable sur le disque").classes(
                    "text-negative text-body2 q-mb-sm"
                )
                ui.label(f"Chemin attendu : {item.stored_path}").classes(
                    "text-caption text-grey-7 q-mb-md"
                )
            else:
                data_url = preview_data_url(item.absolute_path)
                if data_url:
                    ui.image(data_url).classes("w-full rounded-borders q-mb-sm").style(
                        "max-height: 55vh; object-fit: contain;"
                    )
                ui.label(item.filename).classes("text-caption text-grey-7 q-mb-sm")

            if item.tags:
                ui.label("Tags : " + " ".join(f"#{t}" for t in item.tags)).classes(
                    "text-caption q-mb-sm"
                )

            if item.raw_summary:
                ui.textarea(
                    "Résumé",
                    value=item.raw_summary,
                ).props("readonly outlined autogrow").classes("w-full q-mb-md")

            with ui.row().classes("q-gutter-sm"):
                if item.file_exists:

                    def reveal(i: ArchiveItem = item) -> None:
                        try:
                            reveal_in_finder(i.absolute_path)
                        except Exception as exc:
                            ui.notify(str(exc), type="negative")

                    def open_doc(i: ArchiveItem = item) -> None:
                        try:
                            open_file(i.absolute_path)
                        except Exception as exc:
                            ui.notify(str(exc), type="negative")

                    ui.button("Afficher dans le Finder", icon="folder", on_click=reveal).props(
                        "outline"
                    )
                    ui.button("Ouvrir", icon="open_in_new", on_click=open_doc).props(
                        "color=primary unelevated"
                    )

    @ui.refreshable
    def render_category_filters() -> None:
        category_filter_row.clear()
        with category_filter_row:
            ui.label("Filtrer").classes("text-subtitle2 text-grey-7 q-mr-xs")
            for key, label in CATEGORY_OPTIONS.items():

                def set_cat(k: str = key) -> None:
                    state["category"] = k
                    render_category_filters.refresh()
                    render_results.refresh()

                ui.button(label, on_click=set_cat).props(
                    "flat unelevated no-caps"
                ).classes(chip_classes(key, state["category"]))

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
                    render_results.refresh()

                ui.button(f"#{tag}", on_click=select_tag).props(
                    "flat unelevated no-caps"
                ).classes("trankil-tag-suggestion")

    @ui.refreshable
    def render_results() -> None:
        items = search_archives(
            query=state["search"],
            category_filter=state["category"],
            date_from=parse_optional_date(date_from_input.value),
            date_to=parse_optional_date(date_to_input.value),
            sort_desc=state["sort_desc"],
        )

        results_label.text = (
            f"{len(items)} document{'s' if len(items) != 1 else ''} "
            f"trouvé{'s' if len(items) != 1 else ''}"
        )
        results_container.clear()

        with results_container:
            if not items:
                ui.label("Aucun résultat.").classes("text-grey-6 q-pa-md")
                preview_container.clear()
                with preview_container:
                    ui.label("Sélectionnez un document pour l'aperçu.").classes(
                        "text-grey-6 q-pa-lg"
                    )
                return

            selected_id = state["selected"].task_id if state["selected"] else None
            still_visible = any(i.task_id == selected_id for i in items)

            for item in items:
                is_selected = item.task_id == selected_id and still_visible
                card_cls = "w-full q-mb-xs cursor-pointer"
                if is_selected:
                    card_cls += " bg-blue-1"

                def on_select(i: ArchiveItem = item) -> None:
                    show_preview(i)
                    render_results.refresh()

                with ui.card().classes(card_cls).on("click", on_select):
                    with ui.row().classes("items-center no-wrap q-gutter-xs"):
                        ui.label(item.title).classes("text-subtitle2 col ellipsis")
                        if not item.file_exists:
                            ui.badge("Manquant").props("color=red")
                    ui.label(format_date_fr(item.date_emission)).classes(
                        "text-caption text-grey-7"
                    )

            if not still_visible and items:
                show_preview(items[0])
            elif still_visible and state["selected"]:
                show_preview(state["selected"])
            elif items and state["selected"] is None:
                show_preview(items[0])

    def toggle_sort() -> None:
        state["sort_desc"] = not state["sort_desc"]
        sort_toggle.props(
            f'icon={"arrow_downward" if state["sort_desc"] else "arrow_upward"}'
        )
        render_results.refresh()

    sort_toggle.on_click(toggle_sort)

    render_category_filters()
    render_tag_suggestions()
    render_results()

    def refresh_ged() -> None:
        state["search"] = (search_input.value or "").strip()
        render_category_filters.refresh()
        render_tag_suggestions.refresh()
        render_results.refresh()

    register_tab_refresh("ged", refresh_ged)
    return refresh_ged
