"""Vue Paramètres — notifications et Google Calendar."""

from __future__ import annotations

import asyncio

from nicegui import ui

from app.config import CREDENTIALS_PATH
from app.db.connection import get_setting, set_setting
from app.services.calendar_service import CREDENTIALS_FILE, CalendarService


def create_settings_view() -> None:
    """Paramètres application (spec §8, §10)."""
    ui.label("Paramètres").classes("text-h5 q-mb-sm")
    ui.label("Automatisations et intégrations.").classes("text-body2 text-grey-7 q-mb-md")

    calendar = CalendarService()

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Mode Autopilote").classes("text-subtitle1 q-mb-sm")
        ui.label(
            "Activé : les documents analysés deviennent des tâches automatiquement "
            "et le fichier est archivé en GED. Désactivé : validation manuelle dans l'Inbox."
        ).classes("text-caption text-grey-7 q-mb-sm")

        autopilot_switch = ui.switch(
            "Autopilote (validation automatique)",
            value=get_setting("autopilot_enabled", "true") == "true",
        )

        def toggle_autopilot() -> None:
            set_setting("autopilot_enabled", "true" if autopilot_switch.value else "false")
            ui.notify("Préférence Autopilote enregistrée.", type="info")

        autopilot_switch.on("update:model-value", toggle_autopilot)

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Relances anti-oubli").classes("text-subtitle1 q-mb-sm")
        ui.label(
            "Notifications macOS à J-3 et J-1 (application ouverte uniquement)."
        ).classes("text-caption text-grey-7 q-mb-sm")

        notif_switch = ui.switch(
            "Activer les notifications",
            value=get_setting("notification_enabled", "true") == "true",
        )

        def toggle_notifications() -> None:
            set_setting("notification_enabled", "true" if notif_switch.value else "false")
            ui.notify("Préférence enregistrée.", type="info")

        notif_switch.on("update:model-value", toggle_notifications)

    with ui.card().classes("w-full"):
        ui.label("Google Calendar").classes("text-subtitle1 q-mb-sm")
        ui.label("Synchronisation manuelle par défaut. Sync auto optionnelle.").classes(
            "text-caption text-grey-7 q-mb-sm"
        )

        cred_path = ui.label(f"Dossier : {CREDENTIALS_PATH}").classes(
            "text-caption text-grey-8 q-mb-xs"
        )
        cred_path

        if calendar.has_credentials_file():
            ui.label("credentials.json détecté").classes("text-positive text-caption q-mb-xs")
        else:
            ui.label(f"Placez credentials.json dans {CREDENTIALS_FILE}").classes(
                "text-warning text-caption q-mb-xs"
            )

        status = "Connecté" if calendar.is_authenticated() else "Non connecté"
        ui.label(f"Statut : {status}").classes("text-body2 q-mb-sm")

        auto_switch = ui.switch(
            "Sync automatique à la validation Inbox",
            value=get_setting("google_calendar_auto_sync", "false") == "true",
        )

        def toggle_auto_sync() -> None:
            set_setting(
                "google_calendar_auto_sync",
                "true" if auto_switch.value else "false",
            )
            ui.notify("Préférence Calendar enregistrée.", type="info")

        auto_switch.on("update:model-value", toggle_auto_sync)

        with ui.row().classes("q-gutter-sm q-mt-sm"):
            async def authorize_google() -> None:
                try:
                    await asyncio.to_thread(calendar.authorize)
                    ui.notify("Google Calendar connecté.", type="positive")
                except FileNotFoundError as exc:
                    ui.notify(str(exc), type="warning")
                except Exception as exc:
                    ui.notify(f"Authentification échouée : {exc}", type="negative")

            ui.button(
                "Connecter Google Calendar",
                icon="login",
                on_click=authorize_google,
            ).props("outline")

        ui.link(
            "Guide de configuration Google Cloud",
            "#",
            new_tab=False,
        ).classes("text-caption q-mt-md").on(
            "click",
            lambda: ui.notify(
                "Voir la section Google Calendar dans le README du projet.",
                type="info",
            ),
        )

    with ui.card().classes("w-full q-mt-md"):
        ui.label("Données locales").classes("text-subtitle1 q-mb-sm")
        ui.label(
            "Supprime toutes les tâches, documents, tags et l'historique de notifications "
            "de la base SQLite. Les paramètres (Autopilote, clés API, Calendar…) sont "
            "conservés. Les fichiers déjà classés en GED et le dossier .inbox ne sont pas "
            "effacés du disque."
        ).classes("text-caption text-grey-7 q-mb-sm")

        from app.services.db_maintenance import get_application_data_counts, purge_application_data
        from app.services.inbox_queue import get_inbox_queue
        from app.ui.tab_registry import refresh_tab

        stats_label = ui.label("").classes("text-body2 q-mb-sm")

        def refresh_stats() -> None:
            counts = get_application_data_counts()
            stats_label.text = (
                f"{counts['tasks']} tâche(s) · {counts['documents']} document(s) · "
                f"{counts['tags']} tag(s) · {counts['notifications_log']} notification(s)"
            )

        refresh_stats()

        def confirm_purge() -> None:
            counts = get_application_data_counts()
            if counts["tasks"] == 0 and counts["documents"] == 0:
                ui.notify("La base est déjà vide.", type="info")
                return

            with ui.dialog() as dialog, ui.card().classes("q-pa-md"):
                ui.label("Vider la base SQLite ?").classes("text-h6 q-mb-sm")
                ui.label(
                    f"Cette action supprimera définitivement {counts['tasks']} tâche(s) "
                    f"et {counts['documents']} document(s). Elle est irréversible."
                ).classes("text-body2 q-mb-md")
                with ui.row().classes("q-gutter-sm justify-end w-full"):
                    ui.button("Annuler", on_click=dialog.close).props("flat")

                    async def do_purge() -> None:
                        try:
                            removed = await asyncio.to_thread(purge_application_data)
                            get_inbox_queue().clear_all_jobs()
                            refresh_stats()
                            refresh_tab("dashboard")
                            refresh_tab("inbox")
                            refresh_tab("ged")
                            dialog.close()
                            ui.notify(
                                f"Base vidée — {removed['tasks']} tâche(s) supprimée(s).",
                                type="positive",
                            )
                        except Exception as exc:
                            ui.notify(f"Échec : {exc}", type="negative")

                    ui.button(
                        "Vider la base",
                        icon="delete_forever",
                        on_click=do_purge,
                    ).props("color=negative unelevated")

            dialog.open()

        ui.button(
            "Vider la base SQLite",
            icon="delete_forever",
            on_click=confirm_purge,
        ).props("color=negative outline")
