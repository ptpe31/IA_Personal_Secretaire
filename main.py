#!/usr/bin/env python3
"""Point d'entrée Trankil-v2 — NiceGUI local-first."""

from __future__ import annotations

import logging
import sys

from nicegui import ui

from app.config import APP_PORT, APP_TITLE, initialize_app_data
from app.ui.dashboard_view import create_dashboard_view
from app.ui.ged_view import create_ged_view
from app.ui.inbox_view import create_inbox_view

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_header() -> None:
    """En-tête application."""
    with ui.header().classes("items-center justify-between bg-primary text-white"):
        with ui.row().classes("items-center q-gutter-sm"):
            ui.icon("inbox", size="md")
            ui.label(APP_TITLE).classes("text-h6")
        ui.label("Local-first · Données sur votre Mac").classes("text-caption")


def create_shell() -> None:
    """Layout principal avec navigation simplifiée V1."""
    create_header()

    with ui.column().classes("w-full q-pa-md"):
        with ui.tabs().classes("w-full") as tabs:
            inbox_tab = ui.tab("Inbox", icon="inbox")
            dashboard_tab = ui.tab("Tableau de bord", icon="dashboard")
            ged_tab = ui.tab("Archives", icon="folder")

        with ui.tab_panels(tabs, value=inbox_tab).classes("w-full"):
            with ui.tab_panel(inbox_tab):
                create_inbox_view()

            with ui.tab_panel(dashboard_tab):
                create_dashboard_view()

            with ui.tab_panel(ged_tab):
                create_ged_view()


def main() -> None:
    """Initialise données, DB et lance NiceGUI."""
    try:
        initialize_app_data()
        logger.info("Trankil-v2 initialisé — dossiers et base SQLite prêts.")
    except Exception:
        logger.exception("Échec initialisation Trankil-v2")
        sys.exit(1)

    ui.page_title(APP_TITLE)
    create_shell()

    ui.run(
        title=APP_TITLE,
        port=APP_PORT,
        reload=False,
        show=True,
        favicon="📥",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
