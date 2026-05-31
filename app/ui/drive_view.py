"""Vue Menu & Drive — saisie menu, génération IA, robot Drive multi-enseigne."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nicegui import ui

from app.models.drive import (
    DRIVE_PLATFORM_SELECT_OPTIONS,
    DRIVE_PLATFORMS,
    DEFAULT_DRIVE_PLATFORM,
    RAYON_ORDER,
    UNITE_MESURE_OPTIONS,
    CourseItem,
    DriveMenuAnalysisResult,
    DrivePlatformId,
    DriveShoppingItem,
    MEAL_PREFIXES,
    MEAL_SLOTS,
    REGIME_DAYS,
    REGIME_PREFIXES,
    build_drive_menu_input,
    default_meal_textarea_value,
    default_regime_textarea_value,
    determiner_nb_clics,
    format_article_display,
    format_besoin,
    parse_prefixed_textarea,
    platform_id_from_label,
)
from app.services.analysis_client import describe_analysis_engine, get_drive_analysis_client
from app.services.drive_driver_factory import create_drive_driver
from app.services.drive_mapping_service import (
    get_store_mapping,
    normalize_product_url,
    save_mapping_entry,
)
from app.services.drive_pdf_service import render_planning_html, save_planning_pdf
from app.ui.google_theme import CARD_GOOGLE
from app.ui.inbox_ui_safe import element_client_alive, run_if_client_alive
from app.ui.tab_registry import register_tab_refresh

logger = logging.getLogger(__name__)

_DRIVE_TABLE_COLUMNS = [
    {"name": "actif", "label": "", "field": "actif", "align": "center", "style": "width: 44px"},
    {"name": "besoin", "label": "Besoin", "field": "besoin", "align": "right", "style": "width: 80px"},
    {"name": "article", "label": "Article", "field": "article", "align": "left", "style": "min-width: 140px"},
    {
        "name": "contenance",
        "label": "Cont. 1 pqt",
        "field": "contenance",
        "align": "center",
        "style": "width: 88px",
    },
    {"name": "unite", "label": "Unité", "field": "unite", "align": "center", "style": "width: 72px"},
    {"name": "commande", "label": "Commande", "field": "commande", "align": "center", "style": "width: 88px"},
    {"name": "url", "label": "Lien direct", "field": "url", "align": "left", "style": "min-width: 160px"},
    {"name": "rayon", "label": "", "field": "rayon", "style": "display:none"},
]


def create_drive_view():
    """Construit l'onglet Menu & Drive."""
    state: dict[str, Any] = {
        "result": None,
        "row_data": {},
        "table": None,
        "driver": None,
        "robot_task": None,
        "learning_active": False,
        "platform": DEFAULT_DRIVE_PLATFORM,
        "menu_meta": {},
    }

    ui.label("Menu & Drive").classes("text-h5 text-weight-medium text-grey-9 q-mb-xs")
    ui.label(
        "Saisissez vos plats, générez le planning batch cooking et lancez le robot Drive."
    ).classes("text-body2 text-grey-7 q-mb-md")

    anchor = ui.column().classes("w-full")
    with anchor:
        with ui.row().classes("w-full q-col-gutter-md items-start no-wrap"):
            with ui.column().classes("col-7"):
                with ui.card().classes(f"w-full {CARD_GOOGLE}"):
                    ui.label("🍽️ Plats de la semaine (Enfants)").classes("text-subtitle1 q-mb-sm")
                    convives_enfants_input = ui.number(
                        "Nombre de convives (enfants)",
                        value=4,
                        min=1,
                        max=20,
                    ).props("outlined dense").classes("w-full q-mb-sm")
                    meals_input = ui.textarea(value=default_meal_textarea_value()).props(
                        "outlined autogrow rows=14"
                    ).classes("w-full")

            with ui.column().classes("col-5"):
                with ui.card().classes(f"w-full {CARD_GOOGLE}"):
                    ui.label("👥 Extras & Régime").classes("text-subtitle1 q-mb-sm")
                    convives_regime_input = ui.number(
                        "Nombre de convives (régime / extras)",
                        value=4,
                        min=1,
                        max=20,
                    ).props("outlined dense").classes("w-full q-mb-sm")
                    ui.label("Régime spécifique").classes("text-caption text-grey-7")
                    regime_input = ui.textarea(value=default_regime_textarea_value()).props(
                        "outlined autogrow rows=7"
                    ).classes("w-full q-mb-sm")
                    ui.label("Choses à ajouter (Extras)").classes("text-caption text-grey-7")
                    extras_input = ui.textarea(
                        placeholder="rouleau essuie-tout, couches, œufs…"
                    ).props("outlined autogrow rows=4").classes("w-full")

        generate_btn = ui.button(
            "✨ Générer le Planning & le Panier",
            icon="auto_awesome",
        ).props("color=primary unelevated").classes("q-my-md")

        spinner_row = ui.row().classes("items-center q-gutter-sm q-mb-md")
        spinner_row.set_visibility(False)

        results_container = ui.column().classes("w-full")
        results_container.set_visibility(False)

        robot_banner = ui.row().classes(
            "w-full q-pa-sm q-mb-md rounded-borders bg-orange-2 text-orange-10 items-center"
        )
        robot_banner.set_visibility(False)
        with robot_banner:
            ui.icon("warning", color="orange-10")
            robot_banner_label = ui.label("").classes("text-body2")

        status_label = ui.label("").classes("text-body2 text-primary q-mb-sm")
        failures_container = ui.column().classes("w-full q-mb-sm")

        robot_row = ui.row().classes("q-gutter-sm q-mb-md items-center")
        robot_row.set_visibility(False)
        with robot_row:
            resume_btn = ui.button("▶️ DÉMARRER LES COURSES", icon="play_arrow").props(
                "outline color=primary"
            )
            launch_btn = ui.button(
                DRIVE_PLATFORMS[DEFAULT_DRIVE_PLATFORM]["robot_label"],
                icon="smart_toy",
            ).props("color=primary unelevated").classes("shadow-2")
            stop_btn = ui.button("🛑 STOPPER LE ROBOT", icon="stop").props(
                "flat color=negative"
            )
            stop_btn.set_visibility(False)
            skip_btn = ui.button("Passer ce produit", icon="skip_next").props("flat")
            skip_btn.set_visibility(False)

    def _collect_meal_values() -> dict[str, str]:
        return parse_prefixed_textarea(meals_input.value, MEAL_SLOTS, MEAL_PREFIXES)

    def _collect_regime_values() -> dict[str, str]:
        return parse_prefixed_textarea(regime_input.value, REGIME_DAYS, REGIME_PREFIXES)

    def _row_key(course: CourseItem) -> str:
        return f"{course.mot_cle}::{course.unite_recette}"

    def _platform() -> DrivePlatformId:
        return state.get("platform", DEFAULT_DRIVE_PLATFORM)

    def _store_mapping(mot_cle: str) -> dict[str, Any]:
        return dict(get_store_mapping(mot_cle, _platform()) or {})

    def _resolve_row_packaging(
        course: CourseItem,
        mapping: dict[str, Any],
        *,
        url: str,
        row_contenance: float,
        row_unite: str,
    ) -> tuple[float, str]:
        unite = row_unite or mapping.get("unite_paquet") or course.unite_recette
        if not url.strip():
            return 0.0, unite
        if row_contenance > 0:
            return row_contenance, unite
        stored = mapping.get("contenance_paquet") or mapping.get("quantite_paquet")
        if stored:
            return float(stored), unite
        return 0.0, unite

    def _preview_mapping(course: CourseItem, contenance: float, unite: str, mapping: dict[str, Any]) -> dict[str, Any]:
        return {
            **mapping,
            "contenance_paquet": contenance,
            "unite_paquet": unite,
        }

    def _calc_commande(course: CourseItem, contenance: float, unite: str, mapping: dict[str, Any]) -> int:
        return determiner_nb_clics(course, _preview_mapping(course, contenance, unite, mapping))

    def _build_table_row(course: CourseItem, *, actif: bool = True) -> dict[str, Any]:
        row_id = _row_key(course)
        mapping = _store_mapping(course.mot_cle)
        url = mapping.get("product_url", "")
        contenance, unite = _resolve_row_packaging(
            course, mapping, url=url, row_contenance=0.0, row_unite=""
        )
        commande = _calc_commande(course, contenance, unite, mapping)
        state["row_data"][row_id] = {
            "course": course,
            "actif": actif,
            "contenance": contenance,
            "unite": unite,
            "url": url,
            "commande": commande,
        }
        return {
            "id": row_id,
            "actif": actif,
            "besoin": format_besoin(course),
            "article": format_article_display(course),
            "contenance": contenance,
            "unite": unite,
            "commande": commande,
            "url": url,
            "rayon": course.rayon,
        }

    def _refresh_table_rows() -> None:
        table = state.get("table")
        result: DriveMenuAnalysisResult | None = state.get("result")
        if table is None or result is None:
            return
        rows: list[dict[str, Any]] = []
        for rayon in RAYON_ORDER:
            section_items = [c for c in result.liste_courses if c.rayon == rayon]
            if not section_items:
                continue
            rows.append(
                {
                    "id": f"__section__{rayon}",
                    "actif": False,
                    "besoin": "",
                    "article": rayon,
                    "contenance": "",
                    "unite": "",
                    "commande": "",
                    "url": "",
                    "rayon": rayon,
                    "_section": True,
                }
            )
            for course in section_items:
                row_id = _row_key(course)
                previous = state["row_data"].get(row_id, {})
                actif = previous.get("actif", True)
                rows.append(_build_table_row(course, actif=actif))
        table.rows = rows
        table.update()

    def _on_drive_row_update(event) -> None:
        args = event.args or {}
        row_id = args.get("id")
        field = args.get("field")
        value = args.get("value")
        if not row_id or not field or row_id.startswith("__section__"):
            return
        row_data = state["row_data"].get(row_id)
        if row_data is None:
            return
        course: CourseItem = row_data["course"]
        if field == "actif":
            row_data["actif"] = bool(value)
        elif field == "contenance":
            row_data["contenance"] = max(0.0, float(value if value is not None else 0))
            if (row_data.get("url") or "").strip() and row_data["contenance"] > 0:
                save_mapping_entry(
                    course.mot_cle,
                    platform=_platform(),
                    product_name=course.libelle,
                    product_url=normalize_product_url(row_data["url"]),
                    contenance_paquet=row_data["contenance"],
                    unite_paquet=row_data["unite"],
                )
        elif field == "unite":
            row_data["unite"] = str(value)
            if (row_data.get("url") or "").strip():
                save_mapping_entry(
                    course.mot_cle,
                    platform=_platform(),
                    product_name=course.libelle,
                    product_url=normalize_product_url(row_data["url"]),
                    contenance_paquet=row_data["contenance"] if row_data["contenance"] > 0 else None,
                    unite_paquet=row_data["unite"],
                )
        elif field == "url":
            row_data["url"] = str(value or "")
            normalized = normalize_product_url(row_data["url"])
            if normalized:
                row_data["url"] = normalized
                save_mapping_entry(
                    course.mot_cle,
                    platform=_platform(),
                    product_name=course.libelle,
                    product_url=normalized,
                    contenance_paquet=row_data["contenance"] if row_data["contenance"] > 0 else None,
                    unite_paquet=row_data["unite"],
                )
            else:
                row_data["contenance"] = 0.0
        mapping = _store_mapping(course.mot_cle)
        row_data["commande"] = _calc_commande(
            course, row_data["contenance"], row_data["unite"], mapping
        )
        _sync_table_row_from_state(row_id)

    def _sync_table_row_from_state(row_id: str) -> None:
        table = state.get("table")
        row_data = state["row_data"].get(row_id)
        if table is None or row_data is None:
            return
        for row in table.rows:
            if row.get("id") == row_id:
                row["actif"] = row_data["actif"]
                row["contenance"] = row_data["contenance"]
                row["unite"] = row_data["unite"]
                row["url"] = row_data["url"]
                row["commande"] = row_data["commande"]
                break
        table.update()

    def _update_row_url(mot_cle: str, url: str) -> None:
        for row_id, row_data in state.get("row_data", {}).items():
            course: CourseItem = row_data["course"]
            if course.mot_cle == mot_cle:
                row_data["url"] = url
                mapping = _store_mapping(course.mot_cle)
                if not url.strip():
                    row_data["contenance"] = 0.0
                else:
                    contenance, unite = _resolve_row_packaging(
                        course,
                        mapping,
                        url=url,
                        row_contenance=float(row_data.get("contenance", 0)),
                        row_unite=str(row_data.get("unite", course.unite_recette)),
                    )
                    row_data["contenance"] = contenance
                    row_data["unite"] = unite
                row_data["commande"] = _calc_commande(
                    course, row_data["contenance"], row_data["unite"], mapping
                )
                _sync_table_row_from_state(row_id)

    def _get_shopping_items() -> list[DriveShoppingItem]:
        result: DriveMenuAnalysisResult | None = state.get("result")
        if result is None:
            return []
        items: list[DriveShoppingItem] = []
        for row_id, row_data in state.get("row_data", {}).items():
            if not row_data.get("actif", True):
                continue
            course: CourseItem = row_data["course"]
            raw_url = (row_data.get("url") or "").strip()
            if not raw_url:
                raw_url = (_store_mapping(course.mot_cle) or {}).get("product_url", "")
            mapping = _store_mapping(course.mot_cle)
            contenance, unite = _resolve_row_packaging(
                course,
                mapping,
                url=raw_url,
                row_contenance=float(row_data.get("contenance", 0)),
                row_unite=str(row_data.get("unite", course.unite_recette)),
            )
            preview = _preview_mapping(course, contenance, unite, mapping)
            nb_paquets = determiner_nb_clics(course, preview)
            items.append(
                DriveShoppingItem(
                    mot_cle=course.mot_cle,
                    libelle=course.libelle,
                    rayon=course.rayon,
                    quantite_recette=course.quantite_recette,
                    unite_recette=course.unite_recette,
                    product_url=normalize_product_url(raw_url) or None,
                    nb_paquets=nb_paquets,
                )
            )
        return items

    def _set_launch_enabled(enabled: bool) -> None:
        launch_btn.enable() if enabled else launch_btn.disable()

    def _set_resume_enabled(enabled: bool) -> None:
        resume_btn.enable() if enabled else resume_btn.disable()

    def _set_stop_visible(visible: bool) -> None:
        stop_btn.set_visibility(visible)

    def _update_robot_labels() -> None:
        platform = _platform()
        cfg = DRIVE_PLATFORMS[platform]
        launch_btn.text = cfg["robot_label"]
        robot_banner_label.text = (
            f"Connectez-vous dans la fenêtre {cfg['label']} "
            "(magasin Roques pré-sélectionné pour Leclerc), "
            "puis cliquez sur [▶️ Démarrer les courses]."
        )

    def _on_status(message: str) -> None:
        def _update() -> None:
            status_label.text = message
            if "Passer" in message or "Ouvrez la fiche produit" in message:
                skip_btn.set_visibility(True)
                state["learning_active"] = True
            elif state.get("learning_active") and "mémorisé" in message.lower():
                skip_btn.set_visibility(False)
                state["learning_active"] = False

        run_if_client_alive(anchor, _update)

    def _on_failures(products: list[str]) -> None:
        def _update() -> None:
            failures_container.clear()
            with failures_container:
                if products:
                    ui.label("Produits à valider manuellement :").classes("text-subtitle2")
                    for p in products:
                        ui.label(f"• {p}").classes("text-body2")

        run_if_client_alive(anchor, _update)

    def _on_learned(mot_cle: str, url: str) -> None:
        def _update() -> None:
            _update_row_url(mot_cle, url)
            ui.notify(f"Lien mémorisé pour « {mot_cle} ».", type="positive")

        run_if_client_alive(anchor, _update)

    def _configure_drive_table(table) -> None:
        table.add_slot(
            "body-cell-actif",
            r"""
            <q-td :props="props" auto-width class="q-pa-xs">
                <q-checkbox v-if="!props.row._section" dense color="primary"
                    :model-value="props.row.actif"
                    @update:model-value="v => $parent.$emit('driveRowUpdate', { id: props.row.id, field: 'actif', value: v })" />
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-besoin",
            r"""
            <q-td :props="props" class="text-right text-weight-medium text-grey-8">
                <span v-if="!props.row._section">{{ props.row.besoin }}</span>
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-article",
            r"""
            <q-td :props="props">
                <span v-if="props.row._section" class="text-weight-bold text-grey-8">{{ props.row.article }}</span>
                <span v-else class="text-body2">{{ props.row.article }}</span>
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-contenance",
            r"""
            <q-td :props="props" auto-width class="q-pa-xs">
                <q-input v-if="!props.row._section" dense outlined type="number" min="0" step="0.1"
                    style="width:76px;font-size:12px"
                    :model-value="props.row.contenance"
                    @update:model-value="v => $parent.$emit('driveRowUpdate', { id: props.row.id, field: 'contenance', value: v })"
                    @blur="() => $parent.$emit('driveRowUpdate', { id: props.row.id, field: 'contenance', value: props.row.contenance })" />
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-unite",
            r"""
            <q-td :props="props" auto-width class="q-pa-xs">
                <q-select v-if="!props.row._section" dense outlined emit-value map-options
                    style="width:68px;font-size:12px"
                    :options="[{label:'g',value:'g'},{label:'kg',value:'kg'},{label:'ml',value:'ml'},{label:'L',value:'L'},{label:'u',value:'u'}]"
                    :model-value="props.row.unite"
                    @update:model-value="v => $parent.$emit('driveRowUpdate', { id: props.row.id, field: 'unite', value: v })"
                    @blur="() => $parent.$emit('driveRowUpdate', { id: props.row.id, field: 'unite', value: props.row.unite })" />
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-commande",
            r"""
            <q-td :props="props" auto-width class="text-center">
                <span v-if="!props.row._section" class="trankil-drive-commande-badge">{{ props.row.commande }}</span>
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-url",
            r"""
            <q-td :props="props" class="q-pa-xs">
                <q-input v-if="!props.row._section" dense outlined placeholder="URL fiche produit…"
                    style="font-size:12px;min-width:140px"
                    :class="!props.row.url ? 'trankil-drive-url-missing' : ''"
                    :model-value="props.row.url"
                    @update:model-value="v => $parent.$emit('driveRowUpdate', { id: props.row.id, field: 'url', value: v })" />
            </q-td>
            """,
        )
        table.on("driveRowUpdate", _on_drive_row_update)

    def _on_platform_change(event) -> None:
        label = event.value if hasattr(event, "value") else event
        platform = platform_id_from_label(str(label))
        cfg = DRIVE_PLATFORMS[platform]
        if not cfg.get("available"):
            ui.notify(f"{cfg['label']} — bientôt disponible.", type="warning")
            return
        state["platform"] = platform
        _update_robot_labels()
        _refresh_table_rows()

    def show_results(result: DriveMenuAnalysisResult) -> None:
        state["result"] = result
        state["row_data"] = {}
        results_container.clear()
        results_container.set_visibility(True)
        robot_banner.set_visibility(True)
        robot_row.set_visibility(True)
        _update_robot_labels()

        with results_container:
            with ui.row().classes("w-full q-col-gutter-md items-start"):
                with ui.card().classes(f"col-grow {CARD_GOOGLE}").style(
                    "max-height: 70vh; overflow-y: auto"
                ):
                    ui.label("Planning Batch Cooking").classes("text-subtitle1 q-mb-sm")
                    meta = state.get("menu_meta") or {}
                    planning_html = render_planning_html(
                        result,
                        semaine_label=meta.get("semaine_label", ""),
                        nb_convives_enfants=int(meta.get("nb_convives_enfants", 4)),
                        nb_convives_regime=int(meta.get("nb_convives_regime", 4)),
                    )
                    ui.html(planning_html, sanitize=False).classes("w-full")

                    async def save_pdf() -> None:
                        try:
                            meta_local = state.get("menu_meta") or {}
                            path = await asyncio.to_thread(
                                save_planning_pdf,
                                result,
                                semaine_label=meta_local.get("semaine_label", ""),
                                nb_convives_enfants=int(meta_local.get("nb_convives_enfants", 4)),
                                nb_convives_regime=int(meta_local.get("nb_convives_regime", 4)),
                            )
                            ui.notify(f"PDF enregistré : {path.name}", type="positive")
                        except Exception as exc:
                            ui.notify(str(exc), type="negative")

                    ui.button(
                        "🖨️ Imprimer / Sauvegarder en GED",
                        icon="picture_as_pdf",
                        on_click=save_pdf,
                    ).props("outline").classes("q-mt-sm")

                with ui.card().classes(f"col {CARD_GOOGLE}").style("min-width: 0"):
                    ui.label("Liste de courses").classes("text-subtitle1 q-mb-sm")

                    with ui.row().classes(
                        "w-full items-center q-gutter-sm trankil-drive-platform-row"
                    ):
                        ui.label("🛒 Choisir la plateforme de commande :").classes(
                            "text-body2 text-weight-medium text-grey-8"
                        )
                        platform_select = ui.select(
                            DRIVE_PLATFORM_SELECT_OPTIONS,
                            value=DRIVE_PLATFORMS[DEFAULT_DRIVE_PLATFORM]["label"],
                        ).props("outlined dense options-dense").classes("col-grow")
                        platform_select.on("update:model-value", _on_platform_change)

                    rows: list[dict[str, Any]] = []
                    for rayon in RAYON_ORDER:
                        section_items = [c for c in result.liste_courses if c.rayon == rayon]
                        if not section_items:
                            continue
                        rows.append(
                            {
                                "id": f"__section__{rayon}",
                                "actif": False,
                                "besoin": "",
                                "article": rayon,
                                "contenance": "",
                                "unite": "",
                                "commande": "",
                                "url": "",
                                "rayon": rayon,
                                "_section": True,
                            }
                        )
                        for course in section_items:
                            rows.append(_build_table_row(course))

                    table = ui.table(
                        columns=_DRIVE_TABLE_COLUMNS,
                        rows=rows,
                        row_key="id",
                        pagination=0,
                    ).classes("trankil-drive-table w-full").props(
                        "dense flat bordered separator=horizontal wrap-cells=false"
                    )
                    _configure_drive_table(table)
                    state["table"] = table

    async def generate() -> None:
        payload = build_drive_menu_input(
            _collect_meal_values(),
            _collect_regime_values(),
            extras_input.value or "",
            int(convives_enfants_input.value or 4),
            int(convives_regime_input.value or 4),
        )
        if not payload.plats and not payload.extras:
            ui.notify("Saisissez au moins un plat ou un extra.", type="warning")
            return

        generate_btn.disable()
        spinner_row.set_visibility(True)
        spinner_row.clear()
        with spinner_row:
            ui.spinner("dots", size="md", color="primary")
            engine_label = ui.label("Analyse en cours…")

        try:
            client = get_drive_analysis_client()
            engine_label.text = f"Analyse via {describe_analysis_engine(client)}…"
            state["menu_meta"] = {
                "semaine_label": payload.semaine_reference.strftime("%d/%m/%Y"),
                "nb_convives_enfants": payload.nb_convives_enfants,
                "nb_convives_regime": payload.nb_convives_regime,
            }
            result = await asyncio.to_thread(client.analyze_drive_menu, payload)

            def _show() -> None:
                show_results(result)
                ui.notify("Planning et liste de courses générés.", type="positive")

            run_if_client_alive(anchor, _show)
        except RuntimeError as exc:
            ui.notify(str(exc), type="warning")
        except Exception as exc:
            logger.exception("Génération Menu & Drive échouée")
            ui.notify(f"Échec génération : {exc}", type="negative")
        finally:
            generate_btn.enable()
            spinner_row.set_visibility(False)

    async def launch_robot() -> None:
        if state.get("robot_task") and not state["robot_task"].done():
            ui.notify("Le robot est déjà en cours d'exécution.", type="warning")
            return
        platform = _platform()
        cfg = DRIVE_PLATFORMS[platform]
        if not cfg.get("available"):
            ui.notify(f"{cfg['label']} — bientôt disponible.", type="warning")
            return
        items = _get_shopping_items()
        if not items:
            ui.notify("Aucun article sélectionné dans la liste de courses.", type="warning")
            return

        try:
            driver = create_drive_driver(
                platform,
                on_status=_on_status,
                on_failures=_on_failures,
                on_learned=_on_learned,
            )
        except RuntimeError as exc:
            ui.notify(str(exc), type="warning")
            return

        state["driver"] = driver
        _set_launch_enabled(False)
        _set_resume_enabled(True)
        _set_stop_visible(True)

        async def _run() -> None:
            try:
                await driver.run(items)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.exception("Robot Drive en erreur")
                run_if_client_alive(
                    anchor,
                    lambda: ui.notify(f"Robot Drive : {exc}", type="negative"),
                )
            finally:
                def _done() -> None:
                    _set_launch_enabled(True)
                    _set_resume_enabled(True)
                    _set_stop_visible(False)
                    skip_btn.set_visibility(False)
                    state["robot_task"] = None
                    state["driver"] = None

                run_if_client_alive(anchor, _done)

        state["robot_task"] = asyncio.create_task(_run())
        ui.notify(f"{cfg['label']} lancé — fenêtre navigateur ouverte.", type="info")

    async def cancel_robot() -> None:
        task = state.get("robot_task")
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        ui.notify("Robot stoppé.", type="negative")

    async def resume_robot() -> None:
        driver = state.get("driver")
        if driver is None:
            ui.notify(
                f"Lancez d'abord le robot avec [{DRIVE_PLATFORMS[_platform()]['robot_label']}].",
                type="warning",
            )
            return
        await driver.signal_resume()
        _set_resume_enabled(False)
        ui.notify("Courses démarrées — le robot reprend la main.", type="positive")

    async def skip_product() -> None:
        driver = state.get("driver")
        if driver:
            await driver.signal_skip_learning()
            skip_btn.set_visibility(False)
            state["learning_active"] = False

    generate_btn.on("click", generate)
    launch_btn.on("click", launch_robot)
    resume_btn.on("click", resume_robot)
    stop_btn.on("click", cancel_robot)
    skip_btn.on("click", skip_product)

    def refresh_drive() -> None:
        if not element_client_alive(anchor):
            return

    register_tab_refresh("drive", refresh_drive)
    return refresh_drive
