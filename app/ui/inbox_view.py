"""Vue Inbox — drag & drop, split-view, formulaire d'analyse."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from nicegui import events, ui

from app.config import INBOX_PATH
from app.models.analysis import DocumentAnalysis
from app.services.ollama_client import AnalysisClient, get_analysis_client
from app.utils.file_preview import is_allowed_extension, preview_data_url, register_heif_support

logger = logging.getLogger(__name__)

ACCEPT_MIME = ".pdf,.png,.jpg,.jpeg,.webp,.heic"


@dataclass
class InboxState:
    """État de la session Inbox courante."""

    file_path: Path | None = None
    analysis: DocumentAnalysis | None = None
    client: AnalysisClient = field(default_factory=get_analysis_client)


def create_inbox_view() -> None:
    """Construit la Vue 1 Inbox (spec §5)."""
    register_heif_support()
    state = InboxState()

    ui.label("Inbox").classes("text-h5 q-mb-sm")
    ui.label(
        "Déposez un courrier scanné (PDF), une photo iPhone (HEIC) ou une capture d'écran."
    ).classes("text-body2 text-grey-7 q-mb-md")

    mock_banner = ui.row().classes(
        "w-full q-pa-sm q-mb-md rounded-borders bg-orange-2 text-orange-10 items-center"
    )
    with mock_banner:
        ui.icon("warning", color="orange-10")
        mock_label = ui.label("").classes("text-body2")
    mock_banner.set_visibility(False)

    def refresh_mock_banner() -> None:
        if state.client.is_mock:
            mock_label.text = state.client.warning_message or "Mode démo — Ollama non disponible."
            mock_banner.set_visibility(True)
        else:
            mock_banner.set_visibility(False)

    refresh_mock_banner()

    # --- Zone upload ---
    with ui.card().classes("w-full q-mb-md"):
        ui.label("Glisser-déposer un fichier").classes("text-subtitle1 q-mb-sm")
        upload = ui.upload(
            label="Choisir ou déposer (PDF, PNG, JPG, HEIC)",
            auto_upload=True,
            max_files=1,
        ).props(f'accept="{ACCEPT_MIME}" bordered flat').classes("w-full")

    # --- Split view ---
    preview_container = ui.column().classes("w-full")
    form_container = ui.column().classes("w-full")

    with ui.row().classes("w-full q-col-gutter-md no-wrap"):
        with ui.card().classes("col-grow").style("min-width: 45%; max-width: 55%"):
            ui.label("Aperçu du document").classes("text-subtitle1 q-mb-sm")
            with preview_container:
                ui.label("Aucun document — déposez un fichier ci-dessus.").classes(
                    "text-grey-6 q-pa-lg text-center w-full"
                )

        with ui.card().classes("col-grow").style("min-width: 45%"):
            ui.label("Fiche d'analyse").classes("text-subtitle1 q-mb-sm")
            with form_container:
                ui.label("Les champs apparaîtront après l'analyse.").classes("text-grey-6")

    # Références formulaire (remplies dynamiquement)
    form_refs: dict[str, object] = {}

    def clear_form() -> None:
        form_container.clear()
        with form_container:
            ui.label("Analyse en cours…").classes("text-grey-7")

    def render_preview(path: Path) -> None:
        preview_container.clear()
        data_url = preview_data_url(path)
        with preview_container:
            if data_url:
                ui.image(data_url).classes("w-full rounded-borders").style(
                    "max-height: 70vh; object-fit: contain;"
                )
            else:
                ui.label(f"Preview indisponible pour {path.name}").classes("text-negative")
            ui.label(path.name).classes("text-caption text-grey-7 q-mt-sm")

    def render_form(analysis: DocumentAnalysis) -> None:
        form_container.clear()
        form_refs.clear()

        with form_container:
            form_refs["title"] = ui.input("Titre / Action", value=analysis.title).classes("w-full")

            with ui.row().classes("w-full q-col-gutter-sm"):
                form_refs["date_emission"] = ui.input(
                    "Date d'émission",
                    value=analysis.date_emission.isoformat(),
                ).props("type=date").classes("col")
                form_refs["date_event"] = ui.input(
                    "Date événement (optionnel)",
                    value=analysis.date_event.isoformat() if analysis.date_event else "",
                ).props("type=date").classes("col")

            form_refs["deadline"] = ui.input(
                "Deadline",
                value=analysis.deadline.isoformat() if analysis.deadline else "",
            ).props("type=date").classes("w-full")

            ui.label("Catégorie").classes("text-caption text-grey-7")
            form_refs["category"] = ui.radio(
                {"pro": "Pro", "perso": "Perso"},
                value=analysis.category,
            ).props("inline").classes("q-mb-sm")

            form_refs["tags"] = ui.input(
                "Tags (séparés par des virgules)",
                value=", ".join(analysis.tags),
            ).classes("w-full")

            form_refs["raw_summary"] = ui.textarea(
                "Résumé IA",
                value=analysis.raw_summary,
            ).props("readonly outlined autogrow").classes("w-full")

            ui.label(f"Confiance IA : {analysis.confidence:.0%}").classes(
                "text-caption text-grey-7 q-mb-md"
            )

            ui.button(
                "Valider et Classer",
                icon="check",
                on_click=lambda: ui.notify(
                    "Validation GED — implémentée au Sprint 2 (Phase 1 suite).",
                    type="info",
                ),
            ).props("color=primary unelevated").classes("w-full")

    async def process_upload(e: events.UploadEventArguments) -> None:
        filename = e.file.name or "document"
        suffix = Path(filename).suffix.lower()

        if suffix and not is_allowed_extension(Path(filename)):
            ui.notify(f"Format non supporté : {suffix}", type="negative")
            return

        inbox_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
        dest = INBOX_PATH / inbox_name
        INBOX_PATH.mkdir(parents=True, exist_ok=True)

        try:
            content = e.content.read()
            dest.write_bytes(content)
        except Exception as exc:
            logger.exception("Erreur sauvegarde inbox")
            ui.notify(f"Erreur lors de la sauvegarde : {exc}", type="negative")
            return

        state.file_path = dest
        clear_form()
        render_preview(dest)

        ui.notify(f"Analyse de « {filename} » en cours…", type="ongoing")

        try:
            analysis = await asyncio.to_thread(state.client.analyze_document, dest)
        except Exception as exc:
            logger.exception("Analyse échouée")
            ui.notify(f"Analyse échouée : {exc}", type="negative")
            form_container.clear()
            with form_container:
                ui.label("L'analyse a échoué. Réessayez ou vérifiez Ollama.").classes(
                    "text-negative"
                )
            return

        state.analysis = analysis
        render_form(analysis)
        ui.notify("Analyse terminée.", type="positive")

    upload.on_upload(process_upload)

    # Rafraîchir le client au chargement (au cas où Ollama démarre après l'app)
    async def check_ollama_later() -> None:
        await asyncio.sleep(2)
        state.client = get_analysis_client()
        refresh_mock_banner()

    ui.timer(0.1, check_ollama_later, once=True)
