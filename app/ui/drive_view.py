"""Vue Menu & Drive — saisie menu, génération IA, robot Drive multi-enseigne."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from nicegui import ui

from app.config import CURRENT_MENU_PATH

from app.models.drive import (
    DRIVE_PLATFORM_SELECT_OPTIONS,
    DRIVE_PLATFORMS,
    DEFAULT_DRIVE_PLATFORM,
    JOURS_ORDRE_ABSOLU,
    MEAL_PREFIXES,
    PREMIER_JOUR_DEFAUT,
    RAYON_ORDER,
    CourseItem,
    DriveMenuAnalysisResult,
    DrivePlatformId,
    DriveShoppingItem,
    build_drive_menu_input,
    default_meal_textarea_value,
    default_regime_textarea_value,
    determiner_nb_clics,
    drive_menu_input_has_generatable_content,
    format_article_display,
    format_besoin,
    format_prefixed_textarea,
    migrate_regime_creneaux_cibles,
    mirror_planning_to_meals_text,
    mirror_planning_to_regime_text,
    ordered_meal_slots,
    ordered_week_days,
    parse_prefixed_textarea_by_prefix,
    platform_id_from_label,
    PLANNING_MOMENTS,

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
    migrate_row_states_by_platform,
    parse_saved_analysis,
    save_drive_ui_state,
)
from app.ui.google_theme import CARD_GOOGLE
from app.ui.inbox_ui_safe import element_client_alive, run_if_client_alive
from app.ui.tab_registry import register_tab_refresh

logger = logging.getLogger(__name__)

_COMMANDE_PLACEHOLDER = "—"
_LOG_PREFIX = "[DrivePlatform]"
_LOG_TABLE = "[DriveTable]"
_SAVE_DEBOUNCE_S = 0.35


def platform_label_from_event(event: Any) -> str:
    """Extrait le libellé sélectionné depuis un événement NiceGUI (select)."""
    if event is None:
        return ""
    value = getattr(event, "value", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    args = getattr(event, "args", None)
    if isinstance(args, dict):
        label = args.get("label")
        if isinstance(label, str) and label.strip():
            return label.strip()
        idx = args.get("value")
        if isinstance(idx, int) and 0 <= idx < len(DRIVE_PLATFORM_SELECT_OPTIONS):
            return DRIVE_PLATFORM_SELECT_OPTIONS[idx]
    if isinstance(args, str) and args.strip():
        return args.strip()
    if isinstance(args, int) and 0 <= args < len(DRIVE_PLATFORM_SELECT_OPTIONS):
        return DRIVE_PLATFORM_SELECT_OPTIONS[args]
    sender = getattr(event, "sender", None)
    if sender is not None:
        sender_value = getattr(sender, "value", None)
        if isinstance(sender_value, str) and sender_value.strip():
            return sender_value.strip()
    if value is not None and str(value) not in ("", "None"):
        return str(value)
    if isinstance(event, str) and event.strip():
        return event.strip()
    return ""


def url_platform_hint(url: str) -> str:
    """Indique l'enseigne détectée dans une URL (diagnostic)."""
    lower = (url or "").strip().lower()
    if not lower:
        return "vide"
    if "chronodrive.com" in lower:
        return "chronodrive"
    if "leclercdrive" in lower:
        return "leclerc"
    return "autre"

_VALIDATION_TABLE_COLUMNS = [
    {"name": "article", "label": "Article", "field": "article", "align": "left"},
    {"name": "besoin", "label": "Besoin", "field": "besoin", "align": "right"},
    {"name": "contenance", "label": "Cont.", "field": "contenance", "align": "center"},
    {"name": "unite", "label": "Unité", "field": "unite", "align": "center"},
    {"name": "commande", "label": "Commande", "field": "commande", "align": "center"},
]

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


@dataclass
class DriveValidationReport:
    recap_rows: list[dict[str, Any]]
    items: list[DriveShoppingItem]
    active_count: int
    orderable_count: int
    ignored_count: int
    total_paquets: int


def _parse_contenance(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return max(0.0, float(str(value).replace(",", ".").strip()))
    except (TypeError, ValueError):
        return 0.0


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
        "awaiting_login": False,
        "learning_active": False,
        "platform": saved_platform,
        "row_states_by_platform": migrate_row_states_by_platform(saved_ui),
        "menu_meta": dict(saved_ui.get("menu_meta") or {}),
        "save_debounce_task": None,
        "meal_checkboxes": {},
        "regime_checkboxes": {},
        "meal_slot_values": {},
        "regime_slot_values": {},
    }

    def _default_creneaux_selection(premier_jour: str) -> list[str]:
        return list(ordered_meal_slots(premier_jour))

    def _default_regime_selection(premier_jour: str) -> list[str]:
        return list(ordered_meal_slots(premier_jour))

    saved_enfants_mode = saved_ui.get("enfants_mode", "manual")
    if saved_enfants_mode not in ("manual", "consignes"):
        saved_enfants_mode = "manual"
    saved_regime_mode = saved_ui.get("regime_mode", "consignes")
    if saved_regime_mode not in ("manual", "consignes"):
        saved_regime_mode = "consignes"
    saved_meal_creneaux = saved_ui.get("enfants_creneaux_cibles")
    if not isinstance(saved_meal_creneaux, list):
        saved_meal_creneaux = _default_creneaux_selection(saved_premier_jour)
    saved_regime_creneaux = saved_ui.get("regime_creneaux_cibles")
    if not isinstance(saved_regime_creneaux, list):
        legacy = saved_ui.get("regime_jours_cibles")
        if isinstance(legacy, list):
            saved_regime_creneaux = migrate_regime_creneaux_cibles(
                legacy, premier_jour=saved_premier_jour
            )
        else:
            saved_regime_creneaux = _default_regime_selection(saved_premier_jour)

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

        with ui.row().classes("w-full q-col-gutter-sm items-start no-wrap"):
            with ui.column().classes("col-4").style("min-width: 0"):
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
                    ui.label("Créneaux à couvrir").classes("text-caption text-grey-7 q-mb-xs")
                    meal_checkboxes_row = ui.row().classes(
                        "w-full wrap q-gutter-xs q-mb-sm items-start"
                    )
                    enfants_consignes_container = ui.column().classes("w-full")
                    with enfants_consignes_container:
                        ui.label("Consignes pour l'IA").classes("text-caption text-grey-7")
                        enfants_consignes_input = ui.textarea(
                            value=saved_ui.get("enfants_consignes", ""),
                            placeholder="repas pour enfant\npas de lait\ndessert fait maison",
                        ).props("outlined autogrow rows=4").classes("w-full q-mb-sm")
                        reset_enfants_consignes_btn = ui.button(
                            "🧹 Effacer consigne pour l'IA",
                            icon="cleaning_services",
                        ).props("flat color=grey dense").classes("q-mb-sm")
                    ui.label("Template repas").classes("text-caption text-grey-7")
                    meals_input = ui.textarea(
                        value=saved_ui.get("meals_text")
                        or default_meal_textarea_value(saved_premier_jour)
                    ).props("outlined autogrow rows=10").classes("w-full q-mb-sm")
                    reset_enfants_btn = ui.button(
                        "🧹 Effacer cette colonne",
                        icon="cleaning_services",
                    ).props("flat color=grey dense")

            with ui.column().classes("col-4").style("min-width: 0"):
                with ui.card().classes(f"w-full {CARD_GOOGLE}"):
                    ui.label("👥 Régime spécial (hôte additionnel)").classes("text-subtitle1 q-mb-sm")
                    convives_regime_input = ui.number(
                        "Nombre de convives (hôte régime)",
                        value=int(saved_ui.get("convives_regime", 1)),
                        min=1,
                        max=20,
                    ).props("outlined dense").classes("w-full q-mb-sm")
                    regime_mode_radio = ui.radio(
                        {"manual": "Saisie manuelle", "consignes": "Consignes IA"},
                        value=saved_regime_mode,
                    ).props("inline dense").classes("q-mb-sm")
                    ui.label("Créneaux à couvrir").classes("text-caption text-grey-7 q-mb-xs")
                    regime_checkboxes_row = ui.row().classes(
                        "w-full wrap q-gutter-xs q-mb-sm items-start"
                    )
                    regime_consignes_container = ui.column().classes("w-full")
                    with regime_consignes_container:
                        ui.label("Consignes régime pour l'IA").classes("text-caption text-grey-7")
                        regime_consignes_input = ui.textarea(
                            value=saved_ui.get("regime_consignes", ""),
                            placeholder="anti-constipation\nsans lactose\nprotéines poisson le mardi",
                        ).props("outlined autogrow rows=4").classes("w-full q-mb-sm")
                        reset_regime_consignes_btn = ui.button(
                            "🧹 Effacer consigne pour l'IA",
                            icon="cleaning_services",
                        ).props("flat color=grey dense").classes("q-mb-sm")
                    ui.label("Template régime").classes("text-caption text-grey-7")
                    regime_input = ui.textarea(
                        value=saved_ui.get("regime_text")
                        or default_regime_textarea_value(saved_premier_jour)
                    ).props("outlined autogrow rows=10").classes("w-full q-mb-sm")
                    reset_regime_btn = ui.button(
                        "🧹 Effacer cette colonne",
                        icon="cleaning_services",
                    ).props("flat color=grey dense")

            with ui.column().classes("col-4").style("min-width: 0"):
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
            start_courses_btn = ui.button(
                "▶️ DÉMARRER LES COURSES",
                icon="play_arrow",
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
            for day in ordered_week_days(pj):
                with ui.column().classes("items-center q-gutter-y-none q-px-xs"):
                    ui.label(day[:3]).classes(
                        "text-caption text-weight-bold text-grey-8 q-mb-xs"
                    )
                    with ui.row().classes("q-gutter-xs no-wrap"):
                        for moment in PLANNING_MOMENTS:
                            slot = f"{day} {moment.lower()}"
                            short = "M" if moment == "Midi" else "S"
                            cb = ui.checkbox(short, value=slot in selected).props("dense")
                            cb.tooltip(slot)
                            state["meal_checkboxes"][slot] = cb
                            cb.on("update:model-value", lambda _: _on_meal_creneaux_change())

    def _rebuild_regime_checkboxes() -> None:
        pj = _premier_jour()
        selected = {
            slot for slot, cb in state["regime_checkboxes"].items() if cb.value
        }
        if not state["regime_checkboxes"]:
            selected = set(saved_regime_creneaux)
        regime_checkboxes_row.clear()
        state["regime_checkboxes"] = {}
        with regime_checkboxes_row:
            for day in ordered_week_days(pj):
                with ui.column().classes("items-center q-gutter-y-none q-px-xs"):
                    ui.label(day[:3]).classes(
                        "text-caption text-weight-bold text-grey-8 q-mb-xs"
                    )
                    with ui.row().classes("q-gutter-xs no-wrap"):
                        for moment in PLANNING_MOMENTS:
                            slot = f"{day} {moment.lower()}"
                            short = "M" if moment == "Midi" else "S"
                            cb = ui.checkbox(short, value=slot in selected).props("dense")
                            cb.tooltip(slot)
                            state["regime_checkboxes"][slot] = cb
                            cb.on("update:model-value", lambda _: _on_regime_creneaux_change())

    def _collect_meal_creneaux_cibles() -> list[str]:
        return [slot for slot, cb in state["meal_checkboxes"].items() if cb.value]

    def _collect_regime_creneaux_cibles() -> list[str]:
        return [slot for slot, cb in state["regime_checkboxes"].items() if cb.value]

    def _all_meal_keys() -> tuple[str, ...]:
        return tuple(MEAL_PREFIXES.keys())

    def _collect_meal_creneaux_cibles_ordered() -> tuple[str, ...]:
        checked = set(_collect_meal_creneaux_cibles())
        return tuple(slot for slot in ordered_meal_slots(_premier_jour()) if slot in checked)

    def _collect_regime_creneaux_cibles_ordered() -> tuple[str, ...]:
        checked = set(_collect_regime_creneaux_cibles())
        return tuple(slot for slot in ordered_meal_slots(_premier_jour()) if slot in checked)

    def _default_slot_values() -> dict[str, str]:
        return {key: MEAL_PREFIXES[key] for key in MEAL_PREFIXES}

    def _sync_meals_template_display() -> None:
        slots = _collect_meal_creneaux_cibles_ordered()
        cache = state.get("meal_slot_values") or {}
        meals_input.value = format_prefixed_textarea(cache, slots) if slots else ""

    def _sync_regime_template_display() -> None:
        slots = _collect_regime_creneaux_cibles_ordered()
        cache = state.get("regime_slot_values") or {}
        regime_input.value = format_prefixed_textarea(cache, slots) if slots else ""

    def _merge_textarea_into_meal_cache() -> None:
        cache = state.setdefault("meal_slot_values", _default_slot_values())
        prefix_only = {
            slot: MEAL_PREFIXES[slot].strip().rstrip(":") for slot in MEAL_PREFIXES
        }
        for line in (meals_input.value or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            for slot, prefix in MEAL_PREFIXES.items():
                if stripped.startswith(prefix) or stripped == prefix_only[slot]:
                    cache[slot] = line
                    break

    def _merge_textarea_into_regime_cache() -> None:
        cache = state.setdefault("regime_slot_values", _default_slot_values())
        prefix_only = {
            slot: MEAL_PREFIXES[slot].strip().rstrip(":") for slot in MEAL_PREFIXES
        }
        for line in (regime_input.value or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            for slot, prefix in MEAL_PREFIXES.items():
                if stripped.startswith(prefix) or stripped == prefix_only[slot]:
                    cache[slot] = line
                    break

    def _capture_meals_from_textarea() -> None:
        _merge_textarea_into_meal_cache()

    def _capture_regime_from_textarea() -> None:
        _merge_textarea_into_regime_cache()

    def _on_meal_creneaux_change() -> None:
        _capture_meals_from_textarea()
        _sync_meals_template_display()
        _schedule_save()

    def _on_regime_creneaux_change() -> None:
        _capture_regime_from_textarea()
        _sync_regime_template_display()
        _schedule_save()

    def _init_slot_value_caches() -> None:
        all_keys = _all_meal_keys()
        meals_saved = saved_ui.get("meals_text") or default_meal_textarea_value(saved_premier_jour)
        regime_saved = saved_ui.get("regime_text") or default_regime_textarea_value(
            saved_premier_jour
        )
        state["meal_slot_values"] = parse_prefixed_textarea_by_prefix(
            meals_saved, all_keys, MEAL_PREFIXES
        )
        state["regime_slot_values"] = parse_prefixed_textarea_by_prefix(
            regime_saved, all_keys, MEAL_PREFIXES
        )
        _sync_meals_template_display()
        _sync_regime_template_display()

    def _update_enfants_mode_visibility() -> None:
        is_consignes = str(enfants_mode_radio.value) == "consignes"
        enfants_consignes_container.set_visibility(is_consignes)

    def _update_regime_mode_visibility() -> None:
        is_consignes = str(regime_mode_radio.value) == "consignes"
        regime_consignes_container.set_visibility(is_consignes)

    _rebuild_meal_checkboxes()
    _rebuild_regime_checkboxes()
    _init_slot_value_caches()
    _update_enfants_mode_visibility()
    _update_regime_mode_visibility()

    def _collect_meal_values() -> dict[str, str]:
        _capture_meals_from_textarea()
        return dict(state.get("meal_slot_values") or _default_slot_values())

    def _collect_regime_values() -> dict[str, str]:
        _capture_regime_from_textarea()
        return dict(state.get("regime_slot_values") or _default_slot_values())

    def _reorder_saisie_textareas() -> None:
        _capture_meals_from_textarea()
        _capture_regime_from_textarea()
        _rebuild_meal_checkboxes()
        _rebuild_regime_checkboxes()
        _sync_meals_template_display()
        _sync_regime_template_display()
        _schedule_save()

    def _build_save_payload() -> dict[str, Any]:
        _persist_row_states_to_platform()
        payload: dict[str, Any] = {
            "premier_jour_semaine": _premier_jour(),
            "convives_enfants": int(convives_enfants_input.value or 4),
            "convives_regime": int(convives_regime_input.value or 4),
            "enfants_mode": str(enfants_mode_radio.value or "manual"),
            "regime_mode": str(regime_mode_radio.value or "manual"),
            "enfants_consignes": enfants_consignes_input.value or "",
            "regime_consignes": regime_consignes_input.value or "",
            "enfants_creneaux_cibles": _collect_meal_creneaux_cibles(),
            "regime_creneaux_cibles": _collect_regime_creneaux_cibles(),
            "meals_text": meals_input.value or "",
            "regime_text": regime_input.value or "",
            "extras_text": extras_input.value or "",
            "commentaires_text": commentaires_input.value or "",
            "platform": _platform(),
            "menu_meta": dict(state.get("menu_meta") or {}),
            "row_states_by_platform": dict(state.get("row_states_by_platform") or {}),
        }
        result: DriveMenuAnalysisResult | None = state.get("result")
        if result is not None:
            payload["analysis_result"] = result.model_dump(mode="json")
        return payload

    async def _save_current_ui_state() -> None:
        try:
            await asyncio.to_thread(save_drive_ui_state, _build_save_payload())
            logger.info("%s session sauvegardée (current_menu.json)", _LOG_TABLE)
        except Exception:
            logger.exception("%s échec sauvegarde session", _LOG_TABLE)

    def _schedule_save() -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("%s sauvegarde ignorée — pas de boucle asyncio", _LOG_TABLE)
            return

        task = state.get("save_debounce_task")
        if task is not None and not task.done():
            task.cancel()
            logger.debug("%s sauvegarde replanifiée (debounce %.0fms)", _LOG_TABLE, _SAVE_DEBOUNCE_S * 1000)

        async def _debounced() -> None:
            try:
                await asyncio.sleep(_SAVE_DEBOUNCE_S)
                flushed = await _flush_table_to_state()
                if flushed:
                    _log_table_fill_stats("après flush autosave")
                await _save_current_ui_state()
            except asyncio.CancelledError:
                logger.debug("%s sauvegarde annulée (nouvelle édition)", _LOG_TABLE)
            except Exception:
                logger.exception("%s échec autosave", _LOG_TABLE)

        state["save_debounce_task"] = loop.create_task(_debounced())
        logger.debug("%s autosave planifiée dans %.0fms", _LOG_TABLE, _SAVE_DEBOUNCE_S * 1000)

    def _wire_autosave(element, *, event: str = "update:model-value") -> None:
        element.on(event, lambda _: _schedule_save())

    premier_jour_select.on("update:model-value", lambda _: _reorder_saisie_textareas())

    def _row_key(course: CourseItem) -> str:
        return f"{course.mot_cle}::{course.unite_recette}"

    def _platform() -> DrivePlatformId:
        return state.get("platform", DEFAULT_DRIVE_PLATFORM)

    def _url_matches_platform(url: str, platform: DrivePlatformId | None = None) -> bool:
        cleaned = (url or "").strip().lower()
        if not cleaned:
            return True
        platform = platform or _platform()
        if platform == "leclerc":
            return "leclercdrive" in cleaned
        if platform == "chronodrive":
            return "chronodrive.com" in cleaned
        return True

    def _saved_rows_for_platform(platform: DrivePlatformId | None = None) -> dict[str, Any]:
        platform = platform or _platform()
        rows = state.get("row_states_by_platform", {}).get(platform, {})
        return dict(rows) if isinstance(rows, dict) else {}

    def _persist_row_states_to_platform(platform: DrivePlatformId | None = None) -> None:
        platform = platform or _platform()
        row_states: dict[str, Any] = {}
        for row_id, row_data in state.get("row_data", {}).items():
            url = str(row_data.get("url") or "").strip()
            if url and not _url_matches_platform(url, platform):
                url = ""
            row_states[row_id] = {
                "actif": bool(row_data.get("actif", True)),
                "contenance": float(row_data.get("contenance", 0)),
                "unite": str(row_data.get("unite", "")),
                "url": url,
            }
        by_platform = state.setdefault("row_states_by_platform", {})
        by_platform[platform] = row_states
        logger.info(
            "%s persist row_states → %s (%d ligne(s))",
            _LOG_PREFIX,
            platform,
            len(row_states),
        )

    def _log_row_states_by_platform(context: str) -> None:
        by_platform = state.get("row_states_by_platform") or {}
        for platform_id in DRIVE_PLATFORMS:
            rows = by_platform.get(platform_id) or {}
            with_url = sum(1 for r in rows.values() if str(r.get("url") or "").strip())
            logger.info(
                "%s %s | saved[%s] : %d ligne(s), %d URL(s)",
                _LOG_PREFIX,
                context,
                platform_id,
                len(rows),
                with_url,
            )

    def _log_table_snapshot(context: str, *, platform: DrivePlatformId | None = None) -> None:
        platform = platform or _platform()
        table = state.get("table")
        row_data = state.get("row_data") or {}
        samples: list[str] = []
        mismatch = 0
        for row_id, data in list(row_data.items())[:8]:
            course: CourseItem = data["course"]
            url = str(data.get("url") or "")
            hint = url_platform_hint(url)
            if url and hint not in ("vide", platform):
                mismatch += 1
            mapping_url = str((_store_mapping(course.mot_cle) or {}).get("product_url") or "")
            samples.append(
                f"{course.mot_cle!r}: url={url[:60]!r} ({hint}) mapping={mapping_url[:60]!r}"
            )
        table_rows = len(getattr(table, "rows", []) or []) if table else 0
        logger.info(
            "%s %s | platform=%s | row_data=%d | table.rows=%d | mismatch=%d",
            _LOG_PREFIX,
            context,
            platform,
            len(row_data),
            table_rows,
            mismatch,
        )
        for line in samples:
            logger.info("%s   · %s", _LOG_PREFIX, line)

    def _log_table_fill_stats(context: str) -> None:
        row_data = state.get("row_data") or {}
        platform = _platform()
        total = len(row_data)
        with_url = 0
        with_packaging = 0
        commandable = 0
        incomplete: list[str] = []
        for row_id, data in row_data.items():
            course: CourseItem = data["course"]
            url = str(data.get("url") or "").strip()
            contenance = float(data.get("contenance", 0))
            unite = str(data.get("unite") or "").strip()
            if url:
                with_url += 1
            if contenance > 0 and unite:
                with_packaging += 1
            if _row_shopping_item(data) is not None:
                commandable += 1
            elif data.get("actif", True):
                reason = _row_incomplete_reason(data)
                if reason:
                    incomplete.append(f"{course.mot_cle}: {reason}")
        logger.info(
            "%s %s @ %s | %d lignes | %d URL | %d conditionnées | %d commandables",
            _LOG_TABLE,
            context,
            platform,
            total,
            with_url,
            with_packaging,
            commandable,
        )
        for hint in incomplete[:6]:
            logger.info("%s   · incomplet : %s", _LOG_TABLE, hint)
        if len(incomplete) > 6:
            logger.info("%s   · … et %d autre(s)", _LOG_TABLE, len(incomplete) - 6)

    def _row_incomplete_reason(row_data: dict[str, Any]) -> str:
        if not row_data.get("actif", True):
            return ""
        course: CourseItem = row_data["course"]
        raw_url = (row_data.get("url") or "").strip()
        if not raw_url:
            raw_url = str((_store_mapping(course.mot_cle) or {}).get("product_url") or "")
        if not normalize_product_url(raw_url):
            return "URL manquante"
        contenance = float(row_data.get("contenance", 0))
        unite = str(row_data.get("unite") or "").strip()
        mapping = _store_mapping(course.mot_cle)
        if contenance <= 0:
            stored = mapping.get("contenance_paquet") or mapping.get("quantite_paquet")
            if stored:
                contenance = float(stored)
        if not unite:
            unite = str(mapping.get("unite_paquet") or "").strip()
        if contenance <= 0:
            return "contenance manquante"
        if not unite:
            return "unité manquante"
        nb = _calc_commande(course, contenance, unite, mapping)
        if nb <= 0:
            return "quantité incompatible"
        return ""

    def _refresh_row_commande(row_id: str) -> None:
        row_data = state["row_data"].get(row_id)
        if row_data is None:
            return
        course: CourseItem = row_data["course"]
        mapping = _store_mapping(course.mot_cle)
        contenance = float(row_data.get("contenance", 0))
        unite = str(row_data.get("unite") or "").strip()
        if contenance <= 0:
            stored = mapping.get("contenance_paquet") or mapping.get("quantite_paquet")
            if stored:
                contenance = float(stored)
        if not unite:
            unite = str(mapping.get("unite_paquet") or "").strip()
        nb = _calc_commande(course, contenance, unite, mapping)
        commande: int | str = nb if nb > 0 else _COMMANDE_PLACEHOLDER
        _sync_table_fields_inplace(row_id, commande=commande)

    def _apply_row_field_update(row_id: str, field: str, raw_value: Any) -> None:
        row_data = state["row_data"].get(row_id)
        if row_data is None:
            logger.warning("%s ligne inconnue %r (champ %s)", _LOG_TABLE, row_id, field)
            return
        course: CourseItem = row_data["course"]
        mapping = _store_mapping(course.mot_cle)

        if field == "contenance":
            contenance = _parse_contenance(raw_value)
            row_data["contenance"] = contenance
            _sync_table_fields_inplace(row_id, contenance=contenance)
            logger.info(
                "%s %r | contenance → %s",
                _LOG_TABLE,
                course.mot_cle,
                contenance if contenance > 0 else "(vide)",
            )
        elif field == "unite":
            unite = str(raw_value or "").strip()
            row_data["unite"] = unite
            _sync_table_fields_inplace(row_id, unite=unite)
            logger.info("%s %r | unité → %r", _LOG_TABLE, course.mot_cle, unite or "—")
        elif field == "url":
            raw_url = str(raw_value or "").strip()
            if raw_url and not _url_matches_platform(raw_url):
                logger.warning(
                    "%s %r | URL rejetée (enseigne %s) : %s",
                    _LOG_TABLE,
                    course.mot_cle,
                    _platform(),
                    raw_url[:80],
                )
                raw_url = ""
            url = normalize_product_url(raw_url) if raw_url else ""
            row_data["url"] = url
            if url and float(row_data.get("contenance", 0)) <= 0:
                stored = mapping.get("contenance_paquet") or mapping.get("quantite_paquet")
                unite_map = str(mapping.get("unite_paquet") or "")
                if stored:
                    row_data["contenance"] = float(stored)
                    row_data["unite"] = unite_map or row_data.get("unite", "")
                    logger.info(
                        "%s %r | conditionnement repris du mapping : %s %s",
                        _LOG_TABLE,
                        course.mot_cle,
                        row_data["contenance"],
                        row_data["unite"],
                    )
            if url:
                row_data["actif"] = True
            _sync_table_fields_inplace(
                row_id,
                url=url,
                contenance=float(row_data.get("contenance", 0)),
                unite=str(row_data.get("unite") or ""),
                actif=bool(row_data.get("actif", True)),
            )
            logger.info(
                "%s %r | URL → %s",
                _LOG_TABLE,
                course.mot_cle,
                (url[:80] + "…") if len(url) > 80 else url or "(vide)",
            )
        else:
            return

        _refresh_row_commande(row_id)
        nb = state["row_data"][row_id].get("commande", _COMMANDE_PLACEHOLDER)
        if nb != _COMMANDE_PLACEHOLDER:
            logger.debug("%s %r | commande prévisualisée : %s paquet(s)", _LOG_TABLE, course.mot_cle, nb)

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
        unite = row_unite or str(mapping.get("unite_paquet") or "")
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
        if not str(unite or "").strip() or contenance <= 0:
            return 0
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
        url = str(mapping.get("product_url") or "")
        platform = _platform()
        url_source = "mapping" if url else "vide"
        if saved_row:
            saved_url = str(saved_row.get("url") or "").strip()
            if saved_url and _url_matches_platform(saved_url, platform):
                url = saved_url
                url_source = "saved_row"
            elif saved_url:
                url_source = f"saved_row_rejetée({url_platform_hint(saved_url)})"
            contenance = float(saved_row.get("contenance", 0))
            unite = str(saved_row.get("unite") or mapping.get("unite_paquet") or "")
            if actif is None:
                actif = bool(saved_row.get("actif", _default_row_actif(url)))
        else:
            if actif is None:
                actif = _default_row_actif(url)
            contenance, unite = _resolve_row_packaging(
                course, mapping, url=url, row_contenance=0.0, row_unite=""
            )
        logger.debug(
            "%s build_row %s @ %s | source=%s | url=%s",
            _LOG_PREFIX,
            course.mot_cle,
            platform,
            url_source,
            (url[:80] + "…") if len(url) > 80 else url or "(vide)",
        )
        state["row_data"][row_id] = {
            "course": course,
            "actif": actif,
            "contenance": contenance,
            "unite": unite,
            "url": url,
        }
        commande_val = (
            _calc_commande(course, contenance, unite, mapping)
            if contenance > 0 and str(unite or "").strip()
            else 0
        )
        commande: int | str = commande_val if commande_val > 0 else _COMMANDE_PLACEHOLDER
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
            "_platform": platform,
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
                saved_row = _saved_rows_for_platform().get(row_id)
                actif = saved_row.get("actif") if saved_row else None
                rows.append(_build_table_row(course, actif=actif, saved_row=saved_row))
        table.rows = rows
        table.update()
        _log_table_fill_stats("après refresh_table_rows")
        _log_table_snapshot("après refresh_table_rows")
        _schedule_save()

    async def _read_client_table_rows(table) -> list[dict[str, Any]] | None:
        """Lit les lignes du tableau côté client (mutations Vue incluses)."""
        try:
            raw = await table.get_computed_prop("rows", timeout=2.0)
            if isinstance(raw, list):
                return raw
        except Exception:
            logger.debug("%s get_computed_prop('rows') indisponible, repli JS", _LOG_TABLE, exc_info=True)
        js = f"""
            const el = getElement({table.id});
            const qt = el && el.$refs ? el.$refs.qRef : null;
            const raw = (qt && Array.isArray(qt.rows)) ? qt.rows
                : (el && Array.isArray(el.rows)) ? el.rows : [];
            return raw
                .filter(r => r && !r._section)
                .map(r => ({{
                    id: String(r.id),
                    actif: !!r.actif,
                    contenance: r.contenance,
                    unite: r.unite != null ? String(r.unite) : '',
                    url: r.url != null ? String(r.url) : '',
                }}));
        """
        try:
            rows = await table.client.run_javascript(js)
        except Exception:
            logger.exception("%s flush JS échoué", _LOG_TABLE)
            return None
        return rows if isinstance(rows, list) else None

    async def _flush_table_to_state() -> bool:
        table = state.get("table")
        if table is None:
            logger.debug("%s flush ignoré — pas de tableau", _LOG_TABLE)
            return False
        rows = await _read_client_table_rows(table)
        if rows is None:
            return False
        if not rows:
            logger.warning(
                "%s flush | 0 ligne lue — qRef.rows vide (état Python inchangé)",
                _LOG_TABLE,
            )
            return False
        updated = 0
        rejected_urls = 0
        for row in rows:
            if not isinstance(row, dict) or row.get("_section"):
                continue
            row_id = str(row.get("id") or "")
            if not row_id or row_id.startswith("__section__"):
                continue
            payload = row
            row_data = state["row_data"].get(row_id)
            if row_data is None:
                logger.warning("%s flush — ligne JS inconnue côté Python : %s", _LOG_TABLE, row_id)
                continue
            prev_url = str(row_data.get("url") or "")
            prev_cont = float(row_data.get("contenance", 0))
            prev_unite = str(row_data.get("unite") or "")
            row_data["actif"] = bool(payload.get("actif", True))
            row_data["contenance"] = _parse_contenance(payload.get("contenance"))
            row_data["unite"] = str(payload.get("unite") or "").strip()
            raw_url = str(payload.get("url") or "").strip()
            if raw_url and not _url_matches_platform(raw_url):
                rejected_urls += 1
                raw_url = ""
            normalized = normalize_product_url(raw_url) if raw_url else ""
            row_data["url"] = normalized or raw_url
            if (
                prev_url != row_data["url"]
                or prev_cont != row_data["contenance"]
                or prev_unite != row_data["unite"]
            ):
                updated += 1
            _sync_table_fields_inplace(
                row_id,
                actif=row_data["actif"],
                contenance=row_data["contenance"],
                unite=row_data["unite"],
                url=row_data["url"],
            )
            _refresh_row_commande(row_id)
        logger.info(
            "%s flush | %d ligne(s) lues | %d modifiée(s) | %d URL rejetée(s)",
            _LOG_TABLE,
            len(rows),
            updated,
            rejected_urls,
        )
        return True

    def _sync_table_fields_inplace(row_id: str, **fields: Any) -> None:
        table = state.get("table")
        row_data = state["row_data"].get(row_id)
        if table is None or row_data is None:
            return
        for key, value in fields.items():
            row_data[key] = value
        for row in table.rows:
            if row.get("id") == row_id:
                for key, value in fields.items():
                    row[key] = value
                break

    def _on_drive_row_update(event) -> None:
        args = event.args or {}
        row_id = args.get("id")
        field = args.get("field")
        value = args.get("value")
        if not row_id or row_id.startswith("__section__"):
            return
        if field == "actif":
            row_data = state["row_data"].get(row_id)
            if row_data is None:
                return
            row_data["actif"] = bool(value)
            _sync_table_fields_inplace(row_id, actif=row_data["actif"])
            course: CourseItem = row_data["course"]
            logger.info("%s %r | actif → %s", _LOG_TABLE, course.mot_cle, bool(value))
            _refresh_row_commande(row_id)
        elif field in ("contenance", "unite", "url"):
            _apply_row_field_update(row_id, field, value)
        else:
            return
        _schedule_save()

    def _row_shopping_item(row_data: dict[str, Any]) -> DriveShoppingItem | None:
        if not row_data.get("actif", True):
            return None
        course: CourseItem = row_data["course"]
        raw_url = (row_data.get("url") or "").strip()
        if not raw_url:
            raw_url = str((_store_mapping(course.mot_cle) or {}).get("product_url") or "")
        product_url = normalize_product_url(raw_url) or None
        if not product_url:
            return None
        mapping = _store_mapping(course.mot_cle)
        contenance = float(row_data.get("contenance", 0))
        unite = str(row_data.get("unite") or "").strip()
        if not unite:
            unite = str(mapping.get("unite_paquet") or "").strip()
        if contenance <= 0:
            stored = mapping.get("contenance_paquet") or mapping.get("quantite_paquet")
            if stored:
                contenance = float(stored)
        if contenance <= 0 or not unite:
            return None
        nb_paquets = _calc_commande(course, contenance, unite, mapping)
        if nb_paquets <= 0:
            return None
        return DriveShoppingItem(
            mot_cle=course.mot_cle,
            libelle=course.libelle,
            rayon=course.rayon,
            quantite_recette=course.quantite_recette,
            unite_recette=course.unite_recette,
            product_url=product_url,
            nb_paquets=nb_paquets,
        )

    def _build_validation_report() -> DriveValidationReport:
        recap_rows: list[dict[str, Any]] = []
        items: list[DriveShoppingItem] = []
        active_count = 0
        ignored_count = 0
        total_paquets = 0
        for row_data in state.get("row_data", {}).values():
            if not row_data.get("actif", True):
                continue
            active_count += 1
            item = _row_shopping_item(row_data)
            if item is None:
                ignored_count += 1
                continue
            course: CourseItem = row_data["course"]
            mapping = _store_mapping(course.mot_cle)
            contenance = float(row_data.get("contenance", 0))
            unite = str(row_data.get("unite") or mapping.get("unite_paquet") or "").strip()
            if contenance <= 0:
                stored = mapping.get("contenance_paquet") or mapping.get("quantite_paquet")
                if stored:
                    contenance = float(stored)
            total_paquets += item.nb_paquets
            items.append(item)
            recap_rows.append(
                {
                    "article": format_article_display(course),
                    "besoin": format_besoin(course),
                    "contenance": contenance,
                    "unite": unite,
                    "commande": item.nb_paquets,
                }
            )
        return DriveValidationReport(
            recap_rows=recap_rows,
            items=items,
            active_count=active_count,
            orderable_count=len(items),
            ignored_count=ignored_count,
            total_paquets=total_paquets,
        )

    def _log_validation_report(report: DriveValidationReport, *, context: str) -> None:
        logger.info(
            "%s %s | actifs=%d | commandables=%d | ignorés=%d | total %d paquet(s)",
            _LOG_TABLE,
            context,
            report.active_count,
            report.orderable_count,
            report.ignored_count,
            report.total_paquets,
        )

    def _persist_mappings_from_row_data() -> None:
        platform = _platform()
        saved = 0
        skipped = 0
        for row_data in state.get("row_data", {}).values():
            if not row_data.get("actif", True):
                continue
            course: CourseItem = row_data["course"]
            raw_url = (row_data.get("url") or "").strip()
            product_url = normalize_product_url(raw_url)
            if not product_url:
                skipped += 1
                continue
            contenance = float(row_data.get("contenance", 0))
            unite = str(row_data.get("unite") or "").strip()
            if contenance <= 0 or not unite:
                skipped += 1
                continue
            save_mapping_entry(
                course.mot_cle,
                platform=platform,
                product_name=course.libelle,
                product_url=product_url,
                contenance_paquet=contenance,
                unite_paquet=unite,
            )
            saved += 1
        logger.info(
            "%s mapping %s | %d entrée(s) écrite(s) | %d ignorée(s)",
            _LOG_TABLE,
            platform,
            saved,
            skipped,
        )

    async def _open_validation_dialog(
        report: DriveValidationReport,
        *,
        confirm_label: str,
    ) -> bool:
        with ui.dialog() as dialog, ui.card().classes("q-pa-md").style(
            "min-width: 480px; max-width: 720px"
        ):
            ui.label("Valider la liste de courses ?").classes("text-h6 q-mb-sm")
            ui.label(
                f"{report.orderable_count} article(s) commandable(s) · "
                f"{report.total_paquets} paquet(s)"
            ).classes("text-body2 text-grey-8 q-mb-md")
            ui.table(
                columns=_VALIDATION_TABLE_COLUMNS,
                rows=report.recap_rows,
                pagination=0,
            ).props("dense flat bordered").classes("w-full q-mb-md")
            if report.ignored_count > 0:
                ui.label(f"{report.ignored_count} article(s) seront ignorés.").classes(
                    "text-body2 text-orange-9 q-mb-md"
                )
            with ui.row().classes("w-full justify-end q-gutter-sm"):
                ui.button("Non, continuer l'édition", on_click=dialog.close).props("flat")
                ui.button(confirm_label, on_click=lambda: dialog.submit(True)).props(
                    "color=primary unelevated"
                )
        result = await dialog
        return bool(result)

    async def _request_validation(
        *,
        confirm_label: str,
    ) -> DriveValidationReport | None:
        logger.info("%s validation demandée", _LOG_TABLE)
        await _flush_table_to_state()
        _log_table_fill_stats("avant validation")
        report = _build_validation_report()
        _log_validation_report(report, context="rapport validation")
        if report.orderable_count == 0:
            logger.warning("%s validation refusée — aucun article commandable", _LOG_TABLE)
            ui.notify("Aucun article commandable dans la liste de courses.", type="warning")
            return None
        if not await _open_validation_dialog(report, confirm_label=confirm_label):
            logger.info("%s validation annulée par l'utilisateur", _LOG_TABLE)
            return None
        _persist_mappings_from_row_data()
        _schedule_save()
        final = _build_validation_report()
        _log_validation_report(final, context="après commit validation")
        return final

    def _update_row_url(mot_cle: str, url: str) -> None:
        logger.info("%s apprentissage robot | %r → %s", _LOG_TABLE, mot_cle, url[:80] if url else "(vide)")
        for row_id, row_data in state.get("row_data", {}).items():
            course: CourseItem = row_data["course"]
            if course.mot_cle == mot_cle:
                mapping = _store_mapping(course.mot_cle)
                if not url.strip():
                    _sync_table_fields_inplace(
                        row_id,
                        url="",
                        contenance=0.0,
                        actif=False,
                    )
                else:
                    contenance, unite = _resolve_row_packaging(
                        course,
                        mapping,
                        url=url,
                        row_contenance=float(row_data.get("contenance", 0)),
                        row_unite=str(row_data.get("unite", "")),
                    )
                    _sync_table_fields_inplace(
                        row_id,
                        url=url,
                        contenance=contenance,
                        unite=unite,
                        actif=True,
                    )
                _refresh_row_commande(row_id)
                _log_table_fill_stats(f"après apprentissage {mot_cle!r}")
                break

    def _set_start_enabled(enabled: bool) -> None:
        start_courses_btn.enable() if enabled else start_courses_btn.disable()

    def _set_stop_visible(visible: bool) -> None:
        stop_btn.set_visibility(visible)

    def _update_robot_labels() -> None:
        platform = _platform()
        cfg = DRIVE_PLATFORMS[platform]
        robot_banner_label.text = (
            f"Après validation, connectez-vous dans la fenêtre {cfg['label']} "
            "(magasin Roques pré-sélectionné pour Leclerc), "
            "puis recliquez sur [▶️ Démarrer les courses] pour lancer les ajouts au panier."
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
                <q-input v-if="!props.row._section" dense outlined type="text" inputmode="decimal"
                    style="width:76px;font-size:12px"
                    :model-value="props.row.contenance"
                    @update:model-value="v => { props.row.contenance = v }"
                    @blur="$parent.$emit('driveRowUpdate', { id: props.row.id, field: 'contenance', value: props.row.contenance })" />
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-unite",
            r"""
            <q-td :props="props" auto-width class="q-pa-xs">
                <q-select v-if="!props.row._section" dense outlined emit-value map-options
                    style="width:68px;font-size:12px"
                    :options="[{label:'—',value:''},{label:'g',value:'g'},{label:'kg',value:'kg'},{label:'ml',value:'ml'},{label:'L',value:'L'},{label:'u',value:'u'}]"
                    :model-value="props.row.unite"
                    @update:model-value="v => { props.row.unite = v; $parent.$emit('driveRowUpdate', { id: props.row.id, field: 'unite', value: v }) }" />
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-commande",
            r"""
            <q-td :props="props" auto-width class="text-center">
                <span v-if="!props.row._section"
                    :class="props.row.commande === '—' ? 'trankil-drive-commande-badge text-grey-6' : 'trankil-drive-commande-badge text-weight-medium text-primary'">
                    {{ props.row.commande }}
                </span>
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-url",
            r"""
            <q-td :props="props" class="q-pa-xs">
                <q-input v-if="!props.row._section" dense outlined placeholder="URL fiche produit…"
                    :key="props.row.id + '@' + (props.row._platform || '')"
                    style="font-size:12px;min-width:140px"
                    :class="!props.row.url ? 'trankil-drive-url-missing' : ''"
                    :model-value="props.row.url"
                    @update:model-value="v => { props.row.url = v }"
                    @blur="$parent.$emit('driveRowUpdate', { id: props.row.id, field: 'url', value: props.row.url })" />
            </q-td>
            """,
        )
        table.on("driveRowUpdate", _on_drive_row_update)

    async def _on_platform_change(event) -> None:
        logger.info("%s ─── changement magasin demandé ─── event=%r", _LOG_PREFIX, event)
        await _flush_table_to_state()
        old_platform = _platform()
        _log_table_snapshot("avant switch (après flush)", platform=old_platform)
        _persist_row_states_to_platform(old_platform)
        label = platform_label_from_event(event)
        platform = platform_id_from_label(label)
        logger.info(
            "%s parsé label=%r → platform_id=%r (était %r)",
            _LOG_PREFIX,
            label,
            platform,
            old_platform,
        )
        if platform == old_platform:
            logger.warning(
                "%s plateforme inchangée après sélection — label=%r event.args=%r event.value=%r",
                _LOG_PREFIX,
                label,
                getattr(event, "args", None),
                getattr(event, "value", None),
            )
        cfg = DRIVE_PLATFORMS[platform]
        if not cfg.get("available"):
            ui.notify(f"{cfg['label']} — bientôt disponible.", type="warning")
            return
        state["platform"] = platform
        _log_row_states_by_platform("row_states_by_platform avant refresh")
        _update_robot_labels()
        _refresh_table_rows()
        _log_table_snapshot("après switch complet")
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
                        platform_select.on_value_change(_on_platform_change)
                        state["platform_select"] = platform_select

                    saved_rows = restore_rows if restore_rows is not None else _saved_rows_for_platform(platform)
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
                    _log_table_fill_stats("show_results initial")
                    _log_table_snapshot("show_results initial", platform=platform)

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
            regime_creneaux_cibles=_collect_regime_creneaux_cibles(),
        )
        if not drive_menu_input_has_generatable_content(payload):
            ui.notify(
                "Saisissez au moins un plat enfant, des consignes avec créneaux cochés, "
                "un plat/consigne hôte régime, ou un extra.",
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
                mirrored_meals = mirror_planning_to_meals_text(
                    result,
                    premier_jour=pj,
                    existing_values=_collect_meal_values(),
                )
                state["meal_slot_values"] = parse_prefixed_textarea_by_prefix(
                    mirrored_meals, _all_meal_keys(), MEAL_PREFIXES
                )
                _sync_meals_template_display()
                if result.planning_regime:
                    mirrored_regime = mirror_planning_to_regime_text(
                        result,
                        premier_jour=pj,
                        existing_values=_collect_regime_values(),
                    )
                    state["regime_slot_values"] = parse_prefixed_textarea_by_prefix(
                        mirrored_regime, _all_meal_keys(), MEAL_PREFIXES
                    )
                    _sync_regime_template_display()
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

    async def _start_robot(items: list[DriveShoppingItem]) -> None:
        platform = _platform()
        cfg = DRIVE_PLATFORMS[platform]
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
        state["awaiting_login"] = True
        _set_start_enabled(True)
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
                    state["awaiting_login"] = False
                    _set_start_enabled(True)
                    _set_stop_visible(False)
                    skip_btn.set_visibility(False)
                    state["robot_task"] = None
                    state["driver"] = None

                run_if_client_alive(anchor, _done)

        state["robot_task"] = asyncio.create_task(_run())
        ui.notify(f"{cfg['label']} — fenêtre navigateur ouverte.", type="info")

    async def start_courses() -> None:
        platform = _platform()
        cfg = DRIVE_PLATFORMS[platform]
        if not cfg.get("available"):
            ui.notify(f"{cfg['label']} — bientôt disponible.", type="warning")
            return

        driver = state.get("driver")
        robot_task = state.get("robot_task")
        robot_running = robot_task is not None and not robot_task.done()

        if robot_running and driver is None:
            ui.notify("Le robot démarre…", type="info")
            return
        if robot_running and driver is not None and not state.get("awaiting_login", False):
            ui.notify("Les courses sont en cours.", type="warning")
            return

        report = await _request_validation(confirm_label="Oui, démarrer les courses")
        if report is None:
            return

        if driver is None:
            await _start_robot(report.items)
            return

        await driver.signal_resume(report.items)
        state["awaiting_login"] = False
        _set_start_enabled(False)
        ui.notify(
            f"Courses démarrées — {len(report.items)} article(s) synchronisé(s) depuis le tableau.",
            type="positive",
        )

    async def cancel_robot() -> None:
        task = state.get("robot_task")
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        state["awaiting_login"] = False
        ui.notify("Robot stoppé.", type="negative")

    async def skip_product() -> None:
        driver = state.get("driver")
        if driver:
            await driver.signal_skip_learning()
            skip_btn.set_visibility(False)
            state["learning_active"] = False

    async def reset_enfants_col() -> None:
        cache = state.setdefault("meal_slot_values", _default_slot_values())
        for slot in _collect_meal_creneaux_cibles_ordered():
            cache[slot] = MEAL_PREFIXES[slot]
        _sync_meals_template_display()
        await _save_current_ui_state()
        ui.notify("Template repas effacé.", type="info")

    async def reset_enfants_consignes() -> None:
        enfants_consignes_input.value = ""
        await _save_current_ui_state()
        ui.notify("Consignes IA enfants effacées.", type="info")

    async def reset_regime_col() -> None:
        cache = state.setdefault("regime_slot_values", _default_slot_values())
        for slot in _collect_regime_creneaux_cibles_ordered():
            cache[slot] = MEAL_PREFIXES[slot]
        _sync_regime_template_display()
        await _save_current_ui_state()
        ui.notify("Template régime effacé.", type="info")

    async def reset_regime_consignes() -> None:
        regime_consignes_input.value = ""
        await _save_current_ui_state()
        ui.notify("Consignes IA régime effacées.", type="info")

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
        regime_mode_radio.value = "consignes"
        enfants_consignes_input.value = ""
        regime_consignes_input.value = ""
        extras_input.value = ""
        commentaires_input.value = ""
        state["meal_slot_values"] = _default_slot_values()
        state["regime_slot_values"] = _default_slot_values()
        _update_enfants_mode_visibility()
        _update_regime_mode_visibility()
        _rebuild_meal_checkboxes()
        _rebuild_regime_checkboxes()
        _sync_meals_template_display()
        _sync_regime_template_display()
        state["result"] = None
        state["row_data"] = {}
        state["table"] = None
        state["platform_select"] = None
        state["row_states_by_platform"] = {}
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
    reset_enfants_consignes_btn.on("click", reset_enfants_consignes)
    reset_regime_btn.on("click", reset_regime_col)
    reset_regime_consignes_btn.on("click", reset_regime_consignes)
    reset_col3_btn.on("click", reset_col3)
    enfants_mode_radio.on("update:model-value", lambda _: (_update_enfants_mode_visibility(), _schedule_save()))
    regime_mode_radio.on("update:model-value", lambda _: (_update_regime_mode_visibility(), _schedule_save()))
    meals_input.on(
        "update:model-value",
        lambda _: (_capture_meals_from_textarea(), _schedule_save()),
    )
    regime_input.on(
        "update:model-value",
        lambda _: (_capture_regime_from_textarea(), _schedule_save()),
    )
    _wire_autosave(enfants_consignes_input)
    _wire_autosave(regime_consignes_input)
    _wire_autosave(extras_input)
    _wire_autosave(commentaires_input)
    _wire_autosave(convives_enfants_input)
    _wire_autosave(convives_regime_input)
    start_courses_btn.on("click", start_courses)
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
            restore_rows=_saved_rows_for_platform(state.get("platform", DEFAULT_DRIVE_PLATFORM)),
            initial_platform=state.get("platform", DEFAULT_DRIVE_PLATFORM),
        )

    return refresh_drive
