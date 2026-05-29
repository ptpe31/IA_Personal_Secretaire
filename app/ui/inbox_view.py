"""Vue Inbox — drag & drop, collage presse-papiers, split-view."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from nicegui import events, ui

from app.config import INBOX_PATH
from app.models.analysis import DocumentAnalysis
from app.services.calendar_service import try_auto_sync_task
from app.services.inbox_ingest import extension_from_filename
from app.services.ollama_client import AnalysisClient, get_analysis_client
from app.services.task_service import parse_tags_input, validate_inbox_document
from app.utils.dates import parse_optional_date
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
        "Déposez un fichier, ou collez une capture d'écran (⌘V) après avoir cliqué "
        "dans la zone de collage."
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

    # --- Zone collage presse-papiers ---
    with ui.card().classes(
        "w-full q-mb-sm q-pa-md trankil-paste-zone cursor-pointer"
    ).props("flat bordered tabindex=0") as paste_zone:
        with ui.row().classes("items-center q-gutter-sm"):
            ui.icon("content_paste", size="md").classes("text-primary")
            with ui.column():
                ui.label("Coller une capture ou une image").classes("text-subtitle2")
                ui.label("Cliquez ici, puis ⌘V (Mac) ou Ctrl+V").classes(
                    "text-caption text-grey-7"
                )

    # --- Zone upload (drag & drop inchangé) ---
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
                ui.label("Aucun document — déposez ou collez un fichier.").classes(
                    "text-grey-6 q-pa-lg text-center w-full"
                )

        with ui.card().classes("col-grow").style("min-width: 45%"):
            ui.label("Fiche d'analyse").classes("text-subtitle1 q-mb-sm")
            with form_container:
                ui.label("Les champs apparaîtront après l'analyse.").classes("text-grey-6")

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

            def handle_validate() -> None:
                if state.file_path is None or not state.file_path.is_file():
                    ui.notify("Aucun document à valider.", type="warning")
                    return
                try:
                    title = str(form_refs["title"].value or "").strip()
                    date_emission = parse_optional_date(str(form_refs["date_emission"].value))
                    if date_emission is None:
                        raise ValueError("La date d'émission est obligatoire.")
                    date_event = parse_optional_date(str(form_refs["date_event"].value))
                    deadline = parse_optional_date(str(form_refs["deadline"].value))
                    category = str(form_refs["category"].value)
                    tags = parse_tags_input(str(form_refs["tags"].value or ""))
                    raw_summary = str(form_refs["raw_summary"].value or "")

                    task_id = validate_inbox_document(
                        state.file_path,
                        title=title,
                        date_emission=date_emission,
                        date_event=date_event,
                        deadline=deadline,
                        category=category,
                        tags=tags,
                        raw_summary=raw_summary,
                    )
                    state.file_path = None
                    state.analysis = None
                    ui.notify(f"Document classé — tâche #{task_id} créée.", type="positive")
                    if try_auto_sync_task(task_id):
                        ui.notify(
                            "Synchronisé automatiquement avec Google Calendar.",
                            type="positive",
                        )
                    preview_container.clear()
                    with preview_container:
                        ui.label("Document classé. Déposez ou collez un nouveau fichier.").classes(
                            "text-positive q-pa-lg text-center w-full"
                        )
                    form_container.clear()
                    with form_container:
                        ui.label("En attente d'un nouveau document.").classes("text-grey-6")
                except Exception as exc:
                    logger.exception("Validation échouée")
                    ui.notify(f"Erreur lors de la validation : {exc}", type="negative")

            ui.button(
                "Valider et Classer",
                icon="check",
                on_click=handle_validate,
            ).props("color=primary unelevated").classes("w-full")

    async def ingest_inbox_file(dest: Path, filename: str, *, source: str = "upload") -> None:
        """Pipeline commun : preview → analyse Ollama → formulaire."""
        state.file_path = dest
        clear_form()
        render_preview(dest)

        label = "Collage" if source == "paste" else "Import"
        ui.notify(f"{label} de « {filename} » — analyse en cours…", type="ongoing")

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

    async def process_upload(e: events.UploadEventArguments) -> None:
        filename = e.file.name or "document"
        suffix = extension_from_filename(filename)

        if suffix and not is_allowed_extension(Path(filename)):
            ui.notify(f"Format non supporté : {suffix}", type="negative")
            return

        inbox_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
        dest = INBOX_PATH / inbox_name
        INBOX_PATH.mkdir(parents=True, exist_ok=True)

        try:
            await e.file.save(dest)
        except Exception as exc:
            logger.exception("Erreur sauvegarde inbox")
            ui.notify(f"Erreur lors de la sauvegarde : {exc}", type="negative")
            return

        source = "paste" if filename.startswith("paste_") else "upload"
        await ingest_inbox_file(dest, filename, source=source)

    upload.on_upload(process_upload)

    def activate_paste_zone() -> None:
        ui.run_javascript("window.__trankilPasteActive = true")

    def deactivate_paste_zone() -> None:
        ui.run_javascript("window.__trankilPasteActive = false")

    paste_zone.on("click", activate_paste_zone)
    paste_zone.on("focus", activate_paste_zone)
    paste_zone.on("focusin", activate_paste_zone)
    paste_zone.on("focusout", deactivate_paste_zone)

    async def setup_clipboard_paste() -> None:
        upload_url = upload._props["url"]
        await ui.run_javascript(
            f"""
            (function() {{
                if (window.__trankilPasteSetup) return;
                window.__trankilPasteSetup = true;
                window.__trankilUploadUrl = {json.dumps(upload_url)};
                window.__trankilPasteActive = false;

                document.addEventListener('paste', async (event) => {{
                    if (!window.__trankilPasteActive) return;
                    const items = event.clipboardData?.items;
                    if (!items) return;

                    for (const item of items) {{
                        if (!item.type.startsWith('image/')) continue;
                        event.preventDefault();

                        const blob = item.getAsFile();
                        if (!blob) continue;

                        const ext = item.type === 'image/jpeg' ? 'jpg'
                            : item.type === 'image/png' ? 'png'
                            : item.type === 'image/webp' ? 'webp'
                            : 'png';
                        const form = new FormData();
                        form.append('file', blob, `paste_${{Date.now()}}.${{ext}}`);

                        try {{
                            const response = await fetch(window.__trankilUploadUrl, {{
                                method: 'POST',
                                body: form,
                            }});
                            if (!response.ok) {{
                                console.error('Trankil paste upload failed', response.status);
                            }}
                        }} catch (error) {{
                            console.error('Trankil paste error', error);
                        }}
                        break;
                    }}
                }});
            }})();
            """
        )

    ui.timer(0.2, setup_clipboard_paste, once=True)

    async def check_ollama_later() -> None:
        await asyncio.sleep(2)
        state.client = get_analysis_client()
        refresh_mock_banner()

    ui.timer(0.1, check_ollama_later, once=True)
