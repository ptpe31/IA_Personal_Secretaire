"""Vue Menu & Drive — saisie menu, génération IA, robot Drive multi-enseigne."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nicegui import ui

from app.config import CURRENT_MENU_PATH

from app.models.drive import (
    DRIVE_PLATFORM_SELECT_OPTIONS,
    DRIVE_PLATFORMS,
    DEFAULT_DRIVE_PLATFORM,
    JOURS_ORDRE_ABSOLU,
    PREMIER_JOUR_DEFAUT,
    RAYON_ORDER,
    UNITE_MESURE_OPTIONS,
    CourseItem,
    DriveMenuAnalysisResult,
    DrivePlatformId,
    DriveShoppingItem,
    MEAL_PREFIXES,
    MEAL_SLOTS,
    REGIME_PREFIXES,
    build_drive_menu_input,
    default_meal_textarea_value,
    default_regime_textarea_value,
    determiner_nb_clics,
    drive_menu_input_has_generatable_content,
    format_article_display,
    format_besoin,
    format_prefixed_textarea,
    mirror_planning_to_meals_text,
    mirror_regime_consignes_to_text,
    ordered_meal_slots,
    ordered_regime_days,
    parse_prefixed_textarea_by_prefix,
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
from app.services.drive_ui_state import (
    load_drive_ui_state,
    parse_saved_analysis,
    save_drive_ui_state,
)
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
    saved_ui = load_drive_ui_state() or {}
    saved_premier_jour = saved_ui.get("premier_jour_semaine", PREMIER_JOUR_DEFAUT)
    if saved_premier_jour not in JOURS_ORDRE_ABSOLU:
        saved_premier_jour = PREMIER_JOUR_DEFAUT
    saved_platform = saved_ui.get("platform", DEFAULT_DRIVE_PLATFORM)
    if saved_platform not in DRIVE_PLATFORMS:
        saved_platform = DEFAULT_DRIVE_PLATFORM

    state: dict[str, Any] = {
        "result": None,
        "row_data": {},
        "table": None,
        "platform_select": None,
        "driver": None,
        "robot_task": None,
        "learning_active": False,
        "platform": saved_platform,
        "menu_meta": dict(saved_ui.get("menu_meta") or {}),
        "save_debounce_task": None,
        "meal_checkboxes": {},
        "regime_checkboxes": {},
    }

    def _default_creneaux_selection(premier_jour: str) -> list[str]:
        return list(ordered_meal_slots(premier_jour))

    def _default_regime_selection(premier_jour: str) -> list[str]:
        return list(ordered_regime_days(premier_jour))

    saved_enfants_mode = saved_ui.get("enfants_mode", "manual")
    if saved_enfants_mode not in ("manual", "consignes"):
        saved_enfants_mode = "manual"
    saved_regime_mode = saved_ui.get("regime_mode", "manual")
    if saved_regime_mode not in ("manual", "consignes"):
        saved_regime_mode = "manual"
    saved_meal_creneaux = saved_ui.get("enfants_creneaux_cibles")
    if not isinstance(saved_meal_creneaux, list):
        saved_meal_creneaux = _default_creneaux_selection(saved_premier_jour)
    saved_regime_jours = saved_ui.get("regime_jours_cibles")
    if not isinstance(saved_regime_jours, list):
        saved_regime_jours = _default_regime_selection(saved_premier_jour)

    ui.label("Menu & Drive").classes("text-h5 text-weight-medium text-grey-9 q-mb-xs")
    ui.label(
        "Saisissez vos plats ou décrivez vos consignes, générez le planning batch cooking "
        "et lancez le robot Drive."
    ).classes("text-body2 text-grey-7 q-mb-md")

    anchor = ui.column().classes("w-full")
    with anchor:
        premier_jour_select = ui.select(
            label="Premier jour de la semaine",
            options=list(JOURS_ORDRE_ABSOLU),
            value=saved_premier_jour,
        ).classes("w-full mb-4")

        with ui.row().classes("w-full q-col-gutter-md items-start"):
            with ui.column().classes("col-4"):
                with ui.card().classes(f"w-full {CARD_GOOGLE}"):
                    ui.label("🍽️ Plats de la semaine (Enfants)").classes("text-subtitle1 q-mb-sm")
                    convives_enfants_input = ui.number(
                        "Nombre de convives (enfants)",
                        value=int(saved_ui.get("convives_enfants", 4)),
                        min=1,
                        max=20,
                    ).props("outlined dense").classes("w-full q-mb-sm")
                    enfants_mode_radio = ui.radio(
                        {"manual": "Saisie manuelle", "consignes": "Consignes IA"},
                        value=saved_enfants_mode,
                    ).props("inline dense").classes("q-mb-sm")
                    enfants_consignes_container = ui.column().classes("w-full")
                    with enfants_consignes_container:
                        ui.label("Consignes pour l'IA").classes("text-caption text-grey-7")
                        enfants_consignes_input = ui.textarea(
                            value=saved_ui.get("enfants_consignes", ""),
                            placeholder="repas pour enfant\npas de lait\ndessert fait maison",
                        ).props("outlined autogrow rows=4").classes("w-full q-mb-sm")
                        ui.label("Créneaux à générer").classes("text-caption text-grey-7 q-mb-xs")
                        meal_checkboxes_row = ui.row().classes("wrap q-gutter-xs q-mb-sm")
                    ui.label("Template repas").classes("text-caption text-grey-7")
                    meals_input = ui.textarea(
                        value=saved_ui.get("meals_text")
                        or default_meal_textarea_value(saved_premier_jour)
                    ).props("outlined autogrow rows=10").classes("w-full q-mb-sm")
                    reset_enfants_btn = ui.button(
                        "🧹 Effacer cette colonne",
                        icon="cleaning_services",
                    ).props("flat color=grey dense")

            with ui.column().classes("col-4"):
                with ui.card().classes(f"w-full {CARD_GOOGLE}"):
                    ui.label("👥 Régime").classes("text-subtitle1 q-mb-sm")
                    convives_regime_input = ui.number(
                        "Nombre de convives (régime)",
                        value=int(saved_ui.get("convives_regime", 4)),
                        min=1,
                        max=20,
                    ).props("outlined dense").classes("w-full q-mb-sm")
                    regime_mode_radio = ui.radio(
                        {"manual": "Saisie manuelle", "consignes": "Consignes IA"},
                        value=saved_regime_mode,
                    ).props("inline dense").classes("q-mb-sm")
                    regime_consignes_container = ui.column().classes("w-full")
                    with regime_consignes_container:
                        ui.label("Consignes régime pour l'IA").classes("text-caption text-grey-7")
                        regime_consignes_input = ui.textarea(
                            value=saved_ui.get("regime_consignes", ""),
                            placeholder="sans lactose\nprotéines poisson le mardi",
                        ).props("outlined autogrow rows=4").classes("w-full q-mb-sm")
                        ui.label("Jours à couvrir").classes("text-caption text-grey-7 q-mb-xs")
                        regime_checkboxes_row = ui.row().classes("wrap q-gutter-xs q-mb-sm")
                    ui.label("Template régime").classes("text-caption text-grey-7")
                    regime_input = ui.textarea(
                        value=saved_ui.get("regime_text")
                        or default_regime_textarea_value(saved_premier_jour)
                    ).props("outlined autogrow rows=10").classes("w-full q-mb-sm")
                    reset_regime_btn = ui.button(
                        "🧹 Effacer cette colonne",
                        icon="cleaning_services",
                    ).props("flat color=grey dense")

            with ui.column().classes("col-4"):
                with ui.card().classes(f"w-full {CARD_GOOGLE}"):
                    ui.label("📦 Choses à ajouter").classes("text-subtitle1 q-mb-sm")
                    extras_input = ui.textarea(
                        value=saved_ui.get("extras_text", ""),
                        placeholder="rouleau essuie-tout, couches, œufs…",
                    ).props("outlined autogrow rows=8").classes("w-full q-mb-sm")
                    ui.label("Commentaires").classes("text-caption text-grey-7")
                    commentaires_input = ui.textarea(
                        value=saved_ui.get("commentaires_text", ""),
                        placeholder="Notes libres pour la semaine…",
                    ).props("outlined autogrow rows=4").classes("w-full q-mb-sm")
                    reset_col3_btn = ui.button(
                        "🧹 Effacer cette colonne",
                        icon="cleaning_services",
                    ).props("flat color=grey dense")

        with ui.row().classes("q-gutter-sm q-my-md items-center"):
            generate_btn = ui.button(
                "✨ Générer le Planning & le Panier",
                icon="auto_awesome",
            ).props("color=primary unelevated")
            reset_btn = ui.button(
                "🧹 TOUT EFFACER",
                icon="delete_sweep",
            ).props("outline color=grey")

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

    def _premier_jour() -> str:
        return str(premier_jour_select.value or PREMIER_JOUR_DEFAUT)

    def _rebuild_meal_checkboxes() -> None:
        pj = _premier_jour()
        selected = {
            slot
            for slot, cb in state["meal_checkboxes"].items()
            if cb.value
        }
        if not state["meal_checkboxes"]:
            selected = set(saved_meal_creneaux)
        meal_checkboxes_row.clear()
        state["meal_checkboxes"] = {}
        with meal_checkboxes_row:
            for slot in ordered_meal_slots(pj):
                short = slot.replace(" midi", " M").replace(" soir", " S")
                cb = ui.checkbox(short, value=slot in selected).props("dense")
                state["meal_checkboxes"][slot] = cb
                cb.on("update:model-value", lambda _: _schedule_save())

    def _rebuild_regime_checkboxes() -> None:
        pj = _premier_jour()
        selected = {day for day, cb in state["regime_checkboxes"].items() if cb.value}
        if not state["regime_checkboxes"]:
            selected = set(saved_regime_jours)
        regime_checkboxes_row.clear()
        state["regime_checkboxes"] = {}
        with regime_checkboxes_row:
            for day in ordered_regime_days(pj):
                cb = ui.checkbox(day[:3], value=day in selected).props("dense")
                cb.tooltip(day)
                state["regime_checkboxes"][day] = cb
                cb.on("update:model-value", lambda _: _schedule_save())

    def _collect_meal_creneaux_cibles() -> list[str]:
        if str(enfants_mode_radio.value) != "consignes":
            return []
        return [
            slot for slot, cb in state["meal_checkboxes"].items() if cb.value
        ]

    def _collect_regime_jours_cibles() -> list[str]:
        if str(regime_mode_radio.value) != "consignes":
            return []
        return [day for day, cb in state["regime_checkboxes"].items() if cb.value]

    def _update_enfants_mode_visibility() -> None:
        is_consignes = str(enfants_mode_radio.value) == "consignes"
        enfants_consignes_container.set_visibility(is_consignes)

    def _update_regime_mode_visibility() -> None:
        is_consignes = str(regime_mode_radio.value) == "consignes"
        regime_consignes_container.set_visibility(is_consignes)

    _rebuild_meal_checkboxes()
    _rebuild_regime_checkboxes()
    _update_enfants_mode_visibility()
    _update_regime_mode_visibility()

    def _all_meal_keys() -> tuple[str, ...]:
        return tuple(MEAL_PREFIXES.keys())

    def _collect_meal_values() -> dict[str, str]:
        return parse_prefixed_textarea_by_prefix(
            meals_input.value, _all_meal_keys(), MEAL_PREFIXES
        )

    def _collect_regime_values() -> dict[str, str]:
        return parse_prefixed_textarea_by_prefix(
            regime_input.value, tuple(REGIME_PREFIXES.keys()), REGIME_PREFIXES
        )

    def _reorder_saisie_textareas() -> None:
        pj = _premier_jour()
        meals_input.value = format_prefixed_textarea(
            _collect_meal_values(), ordered_meal_slots(pj)
        )
        regime_input.value = format_prefixed_textarea(
            _collect_regime_values(), ordered_regime_days(pj)
        )
        _rebuild_meal_checkboxes()
        _rebuild_regime_checkboxes()
        _schedule_save()

    def _build_save_payload() -> dict[str, Any]:
        row_states: dict[str, Any] = {}
        for row_id, row_data in state.get("row_data", {}).items():
            row_states[row_id] = {
                "actif": bool(row_data.get("actif", True)),
                "contenance": float(row_data.get("contenance", 0)),
                "unite": str(row_data.get("unite", "")),
                "url": str(row_data.get("url", "")),
            }
        payload: dict[str, Any] = {
            "premier_jour_semaine": _premier_jour(),
            "convives_enfants": int(convives_enfants_input.value or 4),
            "convives_regime": int(convives_regime_input.value or 4),
            "enfants_mode": str(enfants_mode_radio.value or "manual"),
            "regime_mode": str(regime_mode_radio.value or "manual"),
            "enfants_consignes": enfants_consignes_input.value or "",
            "regime_consignes": regime_consignes_input.value or "",
            "enfants_creneaux_cibles": _collect_meal_creneaux_cibles(),
            "regime_jours_cibles": _collect_regime_jours_cibles(),
            "meals_text": meals_input.value or "",
            "regime_text": regime_input.value or "",
            "extras_text": extras_input.value or "",
            "commentaires_text": commentaires_input.value or "",
            "platform": _platform(),
            "menu_meta": dict(state.get("menu_meta") or {}),
            "row_states": row_states,
        }
        result: DriveMenuAnalysisResult | None = state.get("result")
        if result is not None:
            payload["analysis_result"] = result.model_dump(mode="json")
        return payload

    async def _save_current_ui_state() -> None:
        await asyncio.to_thread(save_drive_ui_state, _build_save_payload())

    def _schedule_save() -> None:
        task = state.get("save_debounce_task")
        if task is not None and not task.done():
            task.cancel()

        async def _debounced() -> None:
            try:
                await asyncio.sleep(0.35)
                await _save_current_ui_state()
            except asyncio.CancelledError:
                pass

        state["save_debounce_task"] = asyncio.create_task(_debounced())

    def _wire_autosave(element, *, event: str = "update:model-value") -> None:
        element.on(event, lambda _: _schedule_save())

    premier_jour_select.on("update:model-value", lambda _: _reorder_saisie_textareas())

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

    def _default_row_actif(url: str) -> bool:
        return bool((url or "").strip())

    def _build_table_row(
        course: CourseItem,
        *,
        actif: bool | None = None,
        saved_row: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row_id = _row_key(course)
        mapping = _store_mapping(course.mot_cle)
        url = mapping.get("product_url", "")
        if saved_row:
            url = str(saved_row.get("url") or url)
            contenance = float(saved_row.get("contenance", 0))
            unite = str(
                saved_row.get("unite")
                or mapping.get("unite_paquet")
                or course.unite_recette
            )
            if actif is None:
                actif = bool(saved_row.get("actif", _default_row_actif(url)))
        else:
            if actif is None:
                actif = _default_row_actif(url)
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
                previous = state["row_data"].get(row_id)
                actif = previous.get("actif") if previous is not None else None
                rows.append(_build_table_row(course, actif=actif))
        table.rows = rows
        table.update()
        _schedule_save()

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
                row_data["actif"] = True
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
                row_data["actif"] = False
        mapping = _store_mapping(course.mot_cle)
        row_data["commande"] = _calc_commande(
            course, row_data["contenance"], row_data["unite"], mapping
        )
        _sync_table_row_from_state(row_id)
        _schedule_save()

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
                    row_data["actif"] = False
                else:
                    row_data["actif"] = True
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
        _schedule_save()

    def show_results(
        result: DriveMenuAnalysisResult,
        *,
        restore_rows: dict[str, Any] | None = None,
        initial_platform: DrivePlatformId | None = None,
    ) -> None:
        state["result"] = result
        state["row_data"] = {}
        state["platform_select"] = None
        results_container.clear()
        results_container.set_visibility(True)
        robot_banner.set_visibility(True)
        robot_row.set_visibility(True)
        platform = initial_platform or _platform()
        state["platform"] = platform
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
                        premier_jour_semaine=meta.get("premier_jour_semaine", PREMIER_JOUR_DEFAUT),
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
                                premier_jour_semaine=meta_local.get(
                                    "premier_jour_semaine", PREMIER_JOUR_DEFAUT
                                ),
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
                            value=DRIVE_PLATFORMS[platform]["label"],
                        ).props("outlined dense options-dense").classes("col-grow")
                        platform_select.on("update:model-value", _on_platform_change)
                        state["platform_select"] = platform_select

                    saved_rows = restore_rows or {}
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
                            rows.append(
                                _build_table_row(
                                    course,
                                    saved_row=saved_rows.get(row_id),
                                )
                            )

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

        _schedule_save()

    async def generate() -> None:
        payload = build_drive_menu_input(
            _collect_meal_values(),
            _collect_regime_values(),
            extras_input.value or "",
            int(convives_enfants_input.value or 4),
            int(convives_regime_input.value or 4),
            premier_jour_semaine=_premier_jour(),
            enfants_consignes=enfants_consignes_input.value or "",
            enfants_creneaux_cibles=_collect_meal_creneaux_cibles(),
            regime_consignes=regime_consignes_input.value or "",
            regime_jours_cibles=_collect_regime_jours_cibles(),
        )
        if not drive_menu_input_has_generatable_content(payload):
            ui.notify(
                "Saisissez au moins un plat, des consignes avec créneaux cochés, ou un extra.",
                type="warning",
            )
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
                "premier_jour_semaine": payload.premier_jour_semaine,
            }
            result = await asyncio.to_thread(client.analyze_drive_menu, payload)

            def _show() -> None:
                pj = _premier_jour()
                meals_input.value = mirror_planning_to_meals_text(
                    result,
                    premier_jour=pj,
                    existing_values=_collect_meal_values(),
                )
                if str(regime_mode_radio.value) == "consignes" and (
                    regime_consignes_input.value or ""
                ).strip():
                    regime_input.value = mirror_regime_consignes_to_text(
                        premier_jour=pj,
                        existing_values=_collect_regime_values(),
                        regime_consignes=regime_consignes_input.value or "",
                        regime_jours_cibles=_collect_regime_jours_cibles(),
                    )
                show_results(result)
                ui.notify("Planning et liste de courses générés.", type="positive")
                _schedule_save()

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
        updated_items = _get_shopping_items()
        if not updated_items:
            ui.notify("Aucun article coché dans la liste de courses.", type="warning")
            return
        await driver.signal_resume(updated_items)
        _set_resume_enabled(False)
        ui.notify(
            f"Courses démarrées — {len(updated_items)} article(s) synchronisé(s) depuis le tableau.",
            type="positive",
        )

    async def skip_product() -> None:
        driver = state.get("driver")
        if driver:
            await driver.signal_skip_learning()
            skip_btn.set_visibility(False)
            state["learning_active"] = False

    async def reset_enfants_col() -> None:
        pj = _premier_jour()
        enfants_mode_radio.value = "manual"
        enfants_consignes_input.value = ""
        meals_input.value = default_meal_textarea_value(pj)
        _update_enfants_mode_visibility()
        _rebuild_meal_checkboxes()
        await _save_current_ui_state()
        ui.notify("Colonne « Plats enfants » effacée.", type="info")

    async def reset_regime_col() -> None:
        pj = _premier_jour()
        regime_mode_radio.value = "manual"
        regime_consignes_input.value = ""
        regime_input.value = default_regime_textarea_value(pj)
        _update_regime_mode_visibility()
        _rebuild_regime_checkboxes()
        await _save_current_ui_state()
        ui.notify("Colonne « Régime » effacée.", type="info")

    async def reset_col3() -> None:
        extras_input.value = ""
        commentaires_input.value = ""
        await _save_current_ui_state()
        ui.notify("Colonne « Choses à ajouter » effacée.", type="info")

    async def reset_current_week() -> None:
        task = state.get("save_debounce_task")
        if task is not None and not task.done():
            task.cancel()
        if CURRENT_MENU_PATH.is_file():
            CURRENT_MENU_PATH.unlink(missing_ok=True)
        premier_jour_select.value = PREMIER_JOUR_DEFAUT
        convives_enfants_input.value = 4
        convives_regime_input.value = 4
        enfants_mode_radio.value = "manual"
        regime_mode_radio.value = "manual"
        enfants_consignes_input.value = ""
        regime_consignes_input.value = ""
        meals_input.value = default_meal_textarea_value()
        regime_input.value = default_regime_textarea_value()
        extras_input.value = ""
        commentaires_input.value = ""
        _update_enfants_mode_visibility()
        _update_regime_mode_visibility()
        _rebuild_meal_checkboxes()
        _rebuild_regime_checkboxes()
        state["result"] = None
        state["row_data"] = {}
        state["table"] = None
        state["platform_select"] = None
        state["platform"] = DEFAULT_DRIVE_PLATFORM
        state["menu_meta"] = {}
        results_container.clear()
        results_container.set_visibility(False)
        robot_banner.set_visibility(False)
        robot_row.set_visibility(False)
        status_label.text = ""
        failures_container.clear()
        ui.notify("Session réinitialisée.", type="info")

    generate_btn.on("click", generate)
    reset_btn.on("click", reset_current_week)
    reset_enfants_btn.on("click", reset_enfants_col)
    reset_regime_btn.on("click", reset_regime_col)
    reset_col3_btn.on("click", reset_col3)
    enfants_mode_radio.on("update:model-value", lambda _: (_update_enfants_mode_visibility(), _schedule_save()))
    regime_mode_radio.on("update:model-value", lambda _: (_update_regime_mode_visibility(), _schedule_save()))
    _wire_autosave(meals_input)
    _wire_autosave(regime_input)
    _wire_autosave(enfants_consignes_input)
    _wire_autosave(regime_consignes_input)
    _wire_autosave(extras_input)
    _wire_autosave(commentaires_input)
    _wire_autosave(convives_enfants_input)
    _wire_autosave(convives_regime_input)
    launch_btn.on("click", launch_robot)
    resume_btn.on("click", resume_robot)
    stop_btn.on("click", cancel_robot)
    skip_btn.on("click", skip_product)

    def refresh_drive() -> None:
        if not element_client_alive(anchor):
            return

    register_tab_refresh("drive", refresh_drive)

    saved_result = parse_saved_analysis(saved_ui)
    if saved_result is not None:
        show_results(
            saved_result,
            restore_rows=dict(saved_ui.get("row_states") or {}),
            initial_platform=state.get("platform", DEFAULT_DRIVE_PLATFORM),
        )

    return refresh_drive
