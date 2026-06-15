#!/usr/bin/env python3
"""Point d'entrée Trankil-v2 — NiceGUI local-first."""

from __future__ import annotations

import logging
import os
import sys

from nicegui import ui

from app.config import APP_TITLE, initialize_app_data, resolve_listen_port
from app.services.inbox_queue import register_inbox_queue_startup
from app.services.notification_scheduler import start_notification_scheduler
from app.ui.dashboard_view import create_dashboard_view
from app.ui.drive_view import create_drive_view
from app.ui.ged_view import create_ged_view
from app.ui.google_theme import PAGE_BG, apply_google_theme
from app.ui.inbox_view import create_inbox_view
from app.ui.settings_view import create_settings_view
from app.ui.tab_registry import refresh_tab


def _configure_logging() -> None:
    level_name = os.environ.get("TRANKIL_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )


_configure_logging()
logger = logging.getLogger(__name__)


def create_header() -> None:
    """En-tête blanc style Google Workspace."""
    with ui.header().classes("trankil-header q-px-md q-py-sm"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.row().classes("items-center q-gutter-sm"):
                ui.icon("task_alt").classes("text-blue-7").style("font-size: 28px")
                ui.label(APP_TITLE).classes(
                    "text-h5 text-weight-medium text-grey-9"
                ).style("letter-spacing: -0.02em; font-family: inherit")
            ui.label("Local-first · Données sur votre Mac").classes(
                "text-caption text-grey-6"
            )


def create_shell() -> None:
    """Layout principal avec navigation pill-shaped."""
    apply_google_theme()
    create_header()

    with ui.column().classes(f"w-full q-pa-md {PAGE_BG}"):
        with ui.tabs().classes("w-full trankil-nav-tabs q-mb-sm").props(
            "align=left narrow-indicator inline-label no-caps"
        ) as tabs:
            dashboard_tab = ui.tab("Tableau de bord", icon="dashboard")
            inbox_tab = ui.tab("Inbox", icon="inbox")
            ged_tab = ui.tab("Archives", icon="folder")
            drive_tab = ui.tab("Menu & Drive", icon="restaurant")
            settings_tab = ui.tab("Paramètres", icon="settings")

        tab_keys = {
            inbox_tab: "inbox",
            dashboard_tab: "dashboard",
            ged_tab: "ged",
            drive_tab: "drive",
        }

        def switch_to_inbox() -> None:
            tabs.value = inbox_tab
            refresh_tab("inbox")

        with ui.tab_panels(tabs, value=dashboard_tab).classes("w-full bg-transparent"):
            with ui.tab_panel(dashboard_tab):
                create_dashboard_view(switch_to_inbox=switch_to_inbox)

            with ui.tab_panel(inbox_tab):
                create_inbox_view()

            with ui.tab_panel(ged_tab):
                create_ged_view()

            with ui.tab_panel(drive_tab):
                create_drive_view()

            with ui.tab_panel(settings_tab):
                create_settings_view()

        def on_tab_change(event) -> None:
            tab_key = tab_keys.get(event.args)
            if tab_key:
                refresh_tab(tab_key)

        tabs.on("update:model-value", on_tab_change)


def main() -> None:
    """Initialise données, DB et lance NiceGUI."""
    try:
        initialize_app_data()
        start_notification_scheduler()
        logger.info("%s initialisé — dossiers et base SQLite prêts.", APP_TITLE)
    except Exception:
        logger.exception("Échec initialisation %s", APP_TITLE)
        sys.exit(1)

    ui.page_title(APP_TITLE)
    register_inbox_queue_startup()
    create_shell()

    port = resolve_listen_port()
    logger.info("Serveur sur http://localhost:%d", port)

    ui.run(
        title=APP_TITLE,
        port=port,
        reload=False,
        show=True,
        favicon="📥",
    )


if __name__ == "__main__":
    main()
