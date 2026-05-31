"""Vue Menu & Drive — saisie menu, génération IA, robot Leclerc."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nicegui import ui

from app.models.drive import (
    RAYON_ORDER,
    CourseItem,
    DriveMenuAnalysisResult,
    MEAL_SLOTS,
    REGIME_DAYS,
    REGIME_PREFIXES,
    build_drive_menu_input,
    default_meal_input_values,
    default_regime_textarea_value,
)
from app.services.analysis_client import describe_analysis_engine, get_drive_analysis_client
from app.services.drive_pdf_service import save_planning_pdf
from app.services.leclerc_driver import LeclercDriver
from app.ui.google_theme import CARD_GOOGLE
from app.ui.inbox_ui_safe import element_client_alive, run_if_client_alive
from app.ui.tab_registry import register_tab_refresh

logger = logging.getLogger(__name__)


def create_drive_view():
    """Construit l'onglet Menu & Drive."""
    state: dict[str, Any] = {
        "result": None,
        "checkboxes": {},
        "driver": None,
        "robot_task": None,
        "learning_active": False,
    }

    ui.label("Menu & Drive").classes("text-h5 text-weight-medium text-grey-9 q-mb-xs")
    ui.label(
        "Saisissez vos plats, générez le planning batch cooking et lancez le robot Leclerc Drive."
    ).classes("text-body2 text-grey-7 q-mb-md")

    anchor = ui.column().classes("w-full")
    with anchor:
        meal_inputs: dict[str, Any] = {}
        with ui.row().classes("w-full q-col-gutter-md items-start"):
            with ui.card().classes(f"col-grow {CARD_GOOGLE}").style("min-width: 58%"):
                ui.label("🍽️ Plats de la semaine (Enfants)").classes("text-subtitle1 q-mb-sm")
                defaults = default_meal_input_values()
                for slot in MEAL_SLOTS:
                    meal_inputs[slot] = (
                        ui.input(label=slot, value=defaults[slot])
                        .props("outlined dense")
                        .classes("w-full q-mb-xs")
                    )

            with ui.card().classes(f"col {CARD_GOOGLE}").style("min-width: 32%"):
                ui.label("👥 Extras & Régime").classes("text-subtitle1 q-mb-sm")
                convives_input = ui.number(
                    "Nombre de convives",
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
            ui.label(
                "Veuillez vous connecter à votre compte et choisir votre magasin "
                "dans la fenêtre navigateur, puis cliquez sur [▶️ Démarrer les courses]."
            ).classes("text-body2")

        status_label = ui.label("").classes("text-body2 text-primary q-mb-sm")
        failures_container = ui.column().classes("w-full q-mb-sm")

        robot_row = ui.row().classes("q-gutter-sm q-mb-md")
        robot_row.set_visibility(False)
        with robot_row:
            resume_btn = ui.button("▶️ Démarrer les courses", icon="play_arrow").props("outline")
            launch_btn = ui.button(
                "🚀 Lancer le Robot Leclerc Drive",
                icon="smart_toy",
            ).props("color=primary")
            skip_btn = ui.button("Passer ce produit", icon="skip_next").props("flat")
            skip_btn.set_visibility(False)

    def _collect_meal_values() -> dict[str, str]:
        return {slot: meal_inputs[slot].value or "" for slot in MEAL_SLOTS}

    def _collect_regime_values() -> dict[str, str]:
        lines = (regime_input.value or "").splitlines()
        result: dict[str, str] = {}
        for i, day in enumerate(REGIME_DAYS):
            result[day] = lines[i] if i < len(lines) else REGIME_PREFIXES[day]
        return result

    def _get_checked_items() -> list[CourseItem]:
        result: DriveMenuAnalysisResult | None = state.get("result")
        if result is None:
            return []
        checkboxes: dict[str, Any] = state.get("checkboxes", {})
        items: list[CourseItem] = []
        for course in result.liste_courses:
            cb = checkboxes.get(course.mot_cle)
            if cb is None or cb.value:
                items.append(course)
        return items

    def _set_robot_buttons_enabled(enabled: bool) -> None:
        resume_btn.enable() if enabled else resume_btn.disable()
        launch_btn.enable() if enabled else launch_btn.disable()

    def _on_status(message: str) -> None:
        def _update() -> None:
            status_label.text = message
            if "Passer" in message or "Cliquez sur +" in message:
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

    def show_results(result: DriveMenuAnalysisResult) -> None:
        state["result"] = result
        state["checkboxes"] = {}
        results_container.clear()
        results_container.set_visibility(True)
        robot_banner.set_visibility(True)
        robot_row.set_visibility(True)

        with results_container:
            with ui.row().classes("w-full q-col-gutter-md items-start"):
                with ui.card().classes(f"col-grow {CARD_GOOGLE}").style("max-height: 70vh; overflow-y: auto"):
                    ui.label("Planning Batch Cooking").classes("text-subtitle1 q-mb-sm")
                    ui.html(result.planning_html, sanitize=False).classes("w-full")

                    async def save_pdf() -> None:
                        try:
                            path = await asyncio.to_thread(
                                save_planning_pdf,
                                result.planning_html,
                            )
                            ui.notify(f"PDF enregistré : {path.name}", type="positive")
                        except Exception as exc:
                            ui.notify(str(exc), type="negative")

                    ui.button(
                        "🖨️ Imprimer / Sauvegarder en GED",
                        icon="picture_as_pdf",
                        on_click=save_pdf,
                    ).props("outline").classes("q-mt-sm")

                with ui.card().classes(f"col {CARD_GOOGLE}").style("max-height: 70vh; overflow-y: auto"):
                    ui.label("Liste de courses").classes("text-subtitle1 q-mb-sm")
                    by_rayon: dict[str, list] = {r: [] for r in RAYON_ORDER}
                    for course in result.liste_courses:
                        if course.rayon in by_rayon:
                            by_rayon[course.rayon].append(course)
                    for rayon in RAYON_ORDER:
                        items = by_rayon[rayon]
                        if not items:
                            continue
                        ui.label(rayon).classes("text-weight-medium text-grey-8 q-mt-sm")
                        for course in items:
                            cb = ui.checkbox(
                                f"{course.mot_cle} × {course.quantite}",
                                value=True,
                            ).classes("w-full")
                            state["checkboxes"][course.mot_cle] = cb

    async def generate() -> None:
        payload = build_drive_menu_input(
            _collect_meal_values(),
            _collect_regime_values(),
            extras_input.value or "",
            int(convives_input.value or 4),
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
        items = _get_checked_items()
        if not items:
            ui.notify("Aucun article sélectionné dans la liste de courses.", type="warning")
            return

        driver = LeclercDriver(on_status=_on_status, on_failures=_on_failures)
        state["driver"] = driver
        _set_robot_buttons_enabled(False)

        async def _run() -> None:
            try:
                await driver.run(items)
            except Exception as exc:
                logger.exception("Robot Leclerc en erreur")
                run_if_client_alive(
                    anchor,
                    lambda: ui.notify(f"Robot Leclerc : {exc}", type="negative"),
                )
            finally:
                def _done() -> None:
                    _set_robot_buttons_enabled(True)
                    skip_btn.set_visibility(False)
                    state["robot_task"] = None

                run_if_client_alive(anchor, _done)

        state["robot_task"] = asyncio.create_task(_run())
        ui.notify("Robot Leclerc lancé — fenêtre navigateur ouverte.", type="info")

    async def resume_robot() -> None:
        driver: LeclercDriver | None = state.get("driver")
        if driver:
            await driver.signal_resume()
            ui.notify("Robot repris.", type="positive")

    async def skip_product() -> None:
        driver: LeclercDriver | None = state.get("driver")
        if driver:
            await driver.signal_skip_learning()
            skip_btn.set_visibility(False)
            state["learning_active"] = False

    generate_btn.on("click", generate)
    launch_btn.on("click", launch_robot)
    resume_btn.on("click", resume_robot)
    skip_btn.on("click", skip_product)

    def refresh_drive() -> None:
        if not element_client_alive(anchor):
            return

    register_tab_refresh("drive", refresh_drive)
    return refresh_drive
