"""Vue Inbox — drag & drop, collage, file d'attente asynchrone."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from nicegui import events, ui

from app.config import INBOX_PATH
from app.models.analysis import DocumentAnalysis
from app.services.calendar_service import try_auto_sync_task
from app.services.inbox_ingest import extension_from_filename
from app.services.inbox_queue import InboxJob, JobStatus, get_inbox_queue
from app.services.ollama_client import get_analysis_client
from app.services.task_service import parse_tags_input, validate_inbox_document
from app.utils.dates import parse_optional_date
from app.utils.file_preview import is_allowed_extension, preview_data_url, register_heif_support

logger = logging.getLogger(__name__)

ACCEPT_MIME = ".pdf,.png,.jpg,.jpeg,.webp,.heic"

_STATUS_LABELS = {
    JobStatus.QUEUED: ("schedule", "En attente", "grey-7"),
    JobStatus.PROCESSING: ("hourglass_top", "Analyse en cours…", "orange-9"),
    JobStatus.READY: ("check_circle", "Prêt à valider", "positive"),
    JobStatus.FAILED: ("error", "Échec", "negative"),
}


@dataclass
class InboxState:
    active_job_id: str | None = None
    form_job_id: str | None = None


def create_inbox_view() -> None:
    """Construit la Vue 1 Inbox avec file d'attente background."""
    register_heif_support()
    state = InboxState()
    queue = get_inbox_queue()

    ui.label("Inbox").classes("text-h5 q-mb-sm")
    ui.label(
        "Déposez ou collez plusieurs documents : chaque analyse Ollama passe en "
        "arrière-plan pendant que vous continuez."
    ).classes("text-body2 text-grey-7 q-mb-md")

    queue_badge = ui.label("").classes("text-caption text-primary q-mb-sm")

    mock_banner = ui.row().classes(
        "w-full q-pa-sm q-mb-md rounded-borders bg-orange-2 text-orange-10 items-center"
    )
    with mock_banner:
        ui.icon("warning", color="orange-10")
        mock_label = ui.label("").classes("text-body2")
    mock_banner.set_visibility(False)

    client = get_analysis_client()

    def refresh_mock_banner() -> None:
        if client.is_mock:
            mock_label.text = client.warning_message or "Mode démo — Ollama non disponible."
            mock_banner.set_visibility(True)
        else:
            mock_banner.set_visibility(False)

    refresh_mock_banner()

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

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Glisser-déposer un fichier").classes("text-subtitle1 q-mb-sm")
        upload = ui.upload(
            label="Choisir ou déposer (PDF, PNG, JPG, HEIC)",
            auto_upload=True,
            max_files=1,
        ).props(f'accept="{ACCEPT_MIME}" bordered flat').classes("w-full")

    queue_container = ui.column().classes("w-full q-mb-md")

    preview_container = ui.column().classes("w-full")
    form_container = ui.column().classes("w-full")

    with ui.row().classes("w-full q-col-gutter-md no-wrap"):
        with ui.card().classes("col-grow").style("min-width: 45%; max-width: 55%"):
            ui.label("Aperçu du document").classes("text-subtitle1 q-mb-sm")
            with preview_container:
                ui.label("Sélectionnez un document dans la file ou ajoutez-en un.").classes(
                    "text-grey-6 q-pa-lg text-center w-full"
                )

        with ui.card().classes("col-grow").style("min-width: 45%"):
            ui.label("Fiche d'analyse").classes("text-subtitle1 q-mb-sm")
            with form_container:
                ui.label("Les champs apparaîtront quand l'analyse sera prête.").classes(
                    "text-grey-6"
                )

    form_refs: dict[str, object] = {}

    def update_queue_badge() -> None:
        pending = queue.pending_count()
        if pending:
            queue_badge.text = f"{pending} analyse(s) en cours ou en attente"
            queue_badge.set_visibility(True)
        else:
            queue_badge.set_visibility(False)

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

    def render_form_for_job(job: InboxJob) -> None:
        form_container.clear()
        form_refs.clear()
        state.form_job_id = job.id

        if job.status == JobStatus.QUEUED:
            position = queue.queue_position(job.id)
            with form_container:
                ui.label(f"En attente — position {position} dans la file.").classes(
                    "text-grey-7 q-pa-md"
                )
            return

        if job.status == JobStatus.PROCESSING:
            with form_container:
                with ui.row().classes("items-center q-gutter-sm q-pa-md"):
                    ui.spinner("dots", size="md", color="primary")
                    ui.label("Analyse Ollama en arrière-plan…").classes("text-body1")
                ui.label("Vous pouvez ajouter d'autres documents pendant ce temps.").classes(
                    "text-caption text-grey-7"
                )
            return

        if job.status == JobStatus.FAILED:
            with form_container:
                ui.label("L'analyse a échoué.").classes("text-negative text-subtitle2")
                ui.label(job.error or "Erreur inconnue").classes("text-caption q-mb-md")
                ui.button(
                    "Retirer de la file",
                    icon="delete",
                    on_click=lambda: remove_job(job.id),
                ).props("flat color=negative")
            return

        if job.analysis is None:
            return

        analysis = job.analysis
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
                on_click=lambda: handle_validate(job.id),
            ).props("color=primary unelevated").classes("w-full")

    def load_job(job_id: str) -> None:
        job = queue.get_job(job_id)
        if job is None:
            return
        state.active_job_id = job_id
        render_preview(job.file_path)
        render_form_for_job(job)
        render_queue.refresh()

    def remove_job(job_id: str) -> None:
        queue.remove_job(job_id)
        if state.active_job_id == job_id:
            state.active_job_id = None
            state.form_job_id = None
            preview_container.clear()
            with preview_container:
                ui.label("Sélectionnez un document dans la file.").classes("text-grey-6 q-pa-lg")
            form_container.clear()
            with form_container:
                ui.label("En attente d'une sélection.").classes("text-grey-6")
        render_queue.refresh()
        update_queue_badge()

    def handle_validate(job_id: str) -> None:
        job = queue.get_job(job_id)
        if job is None or job.status != JobStatus.READY:
            ui.notify("Document non prêt à valider.", type="warning")
            return
        if state.form_job_id != job_id:
            ui.notify("Ouvrez ce document avant de valider.", type="warning")
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
                job.file_path,
                title=title,
                date_emission=date_emission,
                date_event=date_event,
                deadline=deadline,
                category=category,
                tags=tags,
                raw_summary=raw_summary,
            )
            ui.notify(f"Document classé — tâche #{task_id} créée.", type="positive")
            if try_auto_sync_task(task_id):
                ui.notify("Synchronisé automatiquement avec Google Calendar.", type="positive")
            remove_job(job_id)
        except Exception as exc:
            logger.exception("Validation échouée")
            ui.notify(f"Erreur lors de la validation : {exc}", type="negative")

    def on_queue_changed() -> None:
        render_queue.refresh()
        update_queue_badge()
        if state.active_job_id:
            job = queue.get_job(state.active_job_id)
            if job:
                render_form_for_job(job)

    @ui.refreshable
    def render_queue() -> None:
        queue_container.clear()
        jobs = queue.list_jobs()
        with queue_container:
            if not jobs:
                return
            with ui.card().classes("w-full q-pa-sm"):
                ui.label("File d'analyse").classes("text-subtitle1 q-mb-sm")
                for job in reversed(jobs):
                    icon, label, color = _STATUS_LABELS[job.status]
                    is_active = job.id == state.active_job_id
                    row_cls = "items-center q-gutter-sm q-py-xs rounded-borders q-px-xs"
                    if is_active:
                        row_cls += " bg-blue-1"

                    with ui.row().classes(row_cls):

                        def open_job(jid: str = job.id) -> None:
                            load_job(jid)

                        ui.button(icon=icon, on_click=open_job).props(
                            f"flat dense round color={color}"
                        )
                        with ui.column().classes("col cursor-pointer").on("click", open_job):
                            ui.label(job.filename).classes("text-body2 ellipsis")
                            ui.label(label).classes(f"text-caption text-{color}")
                        if job.status in (JobStatus.READY, JobStatus.FAILED):
                            ui.button(
                                icon="close",
                                on_click=lambda jid=job.id: remove_job(jid),
                            ).props("flat dense round size=sm").tooltip("Retirer")

    def enqueue_file(dest: Path, filename: str, *, source: str) -> None:
        job = queue.enqueue(dest, filename, source=source)
        position = queue.queue_position(job.id)
        label = "Collage" if source == "paste" else "Import"
        ui.notify(
            f"{label} « {filename} » — ajouté à la file (position {position}).",
            type="ongoing",
            timeout=4000,
        )
        upload.reset()
        render_queue.refresh()
        update_queue_badge()
        if state.active_job_id is None:
            load_job(job.id)

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
        enqueue_file(dest, filename, source=source)

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
                            await fetch(window.__trankilUploadUrl, {{
                                method: 'POST',
                                body: form,
                            }});
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
    ui.timer(2.0, refresh_mock_banner, once=True)

    queue.add_listener(on_queue_changed)
    render_queue()
    update_queue_badge()
