"""Vue Inbox — drag & drop, collage, file d'attente asynchrone."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from nicegui import events, ui

from app.config import INBOX_PATH
from app.models.analysis import DocumentAnalysisResult
from app.services.calendar_service import try_auto_sync_task
from app.services.inbox_ingest import extension_from_filename
from app.services.inbox_queue import InboxJob, JobStatus, get_inbox_queue
from app.services.ollama_client import get_analysis_client
from app.services.task_service import TaskValidationInput, parse_tags_input, validate_inbox_tasks
from app.ui.document_upload import ACCEPT_MIME, create_paste_zone, wire_clipboard_paste
from app.ui.inbox_ui_safe import element_client_alive, run_if_client_alive, safe_clear
from app.ui.tab_registry import register_tab_refresh
from app.utils.dates import parse_optional_date
from app.utils.file_preview import is_allowed_extension, preview_data_url, register_heif_support

logger = logging.getLogger(__name__)

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


def _display_filename(path: Path) -> str:
    name = path.name
    prefix, _, rest = name.partition("_")
    if len(prefix) == 32 and rest:
        return rest
    return name


def create_inbox_view():
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

    paste_zone = create_paste_zone()
    paste_zone.classes(add="q-mb-sm")

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

    with ui.row().classes("w-full q-col-gutter-md items-start"):
        with ui.card().classes("col-grow").style(
            "min-width: 42%; max-width: 48%; max-height: 82vh; overflow-y: auto;"
        ):
            ui.label("Aperçu du document").classes("text-subtitle1 q-mb-sm")
            with preview_container:
                ui.label("Sélectionnez un document dans la file ou ajoutez-en un.").classes(
                    "text-grey-6 q-pa-lg text-center w-full"
                )

        with ui.card().classes("col-grow").style(
            "min-width: 42%; max-height: 82vh; overflow-y: auto;"
        ):
            ui.label("Fiches d'analyse").classes("text-subtitle1 q-mb-sm")
            with form_container:
                ui.label("Les fiches apparaîtront quand l'analyse sera prête.").classes(
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

    def _detach_queue_listener() -> None:
        queue.remove_listener(on_queue_changed)
        logger.debug("Listener file Inbox désenregistré (client déconnecté).")

    def render_preview(path: Path) -> None:
        if not safe_clear(preview_container):
            return
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
        if not safe_clear(form_container):
            return
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

        result: DocumentAnalysisResult = job.analysis
        active_tasks = [
            (idx, task)
            for idx, task in enumerate(result.tasks)
            if idx not in job.excluded_task_indices
        ]

        with form_container:
            ui.label(
                f"{len(active_tasks)} fiche(s) sur {len(result.tasks)} détectée(s)"
            ).classes("text-subtitle2 q-mb-sm")

            form_refs["document_summary"] = ui.textarea(
                "Résumé du document",
                value=result.document_summary,
            ).props("outlined autogrow").classes("w-full q-mb-md")

            ui.label(f"Confiance IA globale : {result.confidence:.0%}").classes(
                "text-caption text-grey-7 q-mb-md"
            )

            for idx, task in active_tasks:
                card_key = f"{job.id}_{idx}"
                with ui.card().classes("w-full q-mb-sm q-pa-sm"):
                    with ui.row().classes("items-center justify-between q-mb-xs"):
                        ui.label(f"Fiche {idx + 1}").classes("text-caption text-grey-7")
                        ui.button(
                            icon="close",
                            on_click=lambda i=idx, jid=job.id: exclude_task_card(jid, i),
                        ).props("flat dense round size=sm color=negative").tooltip(
                            "Retirer cette fiche"
                        )

                    form_refs[f"{card_key}_title"] = ui.input(
                        "Titre / Action",
                        value=task.title,
                    ).classes("w-full")

                    with ui.row().classes("w-full q-col-gutter-sm"):
                        form_refs[f"{card_key}_date_emission"] = ui.input(
                            "Date d'émission",
                            value=task.date_emission.isoformat(),
                        ).props("type=date").classes("col")
                        form_refs[f"{card_key}_date_event"] = ui.input(
                            "Date événement (optionnel)",
                            value=task.date_event.isoformat() if task.date_event else "",
                        ).props("type=date").classes("col")

                    form_refs[f"{card_key}_deadline"] = ui.input(
                        "Deadline / Événement",
                        value=task.deadline.isoformat() if task.deadline else "",
                    ).props("type=date").classes("w-full")

                    form_refs[f"{card_key}_suggestion"] = ui.input(
                        label="Suggestion IA",
                        value=task.suggestion or "",
                        placeholder="Action immédiate ou rappel logistique…",
                    ).props("outlined").classes("w-full q-mb-sm")

                    ui.label("Catégorie").classes("text-caption text-grey-7")
                    form_refs[f"{card_key}_category"] = ui.radio(
                        {"pro": "Pro", "perso": "Perso"},
                        value=task.category,
                    ).props("inline").classes("q-mb-sm")

                    form_refs[f"{card_key}_tags"] = ui.input(
                        "Tags (séparés par des virgules)",
                        value=", ".join(task.tags),
                    ).classes("w-full")

                    if task.justification_proof and task.justification_proof != "Aucune":
                        ui.label(f"Preuve IA : « {task.justification_proof} »").classes(
                            "text-caption text-grey-6 q-mt-xs italic"
                        )

            if not active_tasks:
                ui.label("Aucune fiche sélectionnée — rouvrez le document ou retirez-le.").classes(
                    "text-grey-7 q-mb-md"
                )
            else:
                count = len(active_tasks)
                ui.button(
                    f"Valider les {count} tâche{'s' if count > 1 else ''}",
                    icon="check",
                    on_click=lambda: handle_validate(job.id),
                ).props("color=primary unelevated").classes("w-full q-mt-md")

    def exclude_task_card(job_id: str, task_index: int) -> None:
        job = queue.get_job(job_id)
        if job is None:
            return
        job.excluded_task_indices.add(task_index)
        render_form_for_job(job)

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
            if safe_clear(preview_container):
                with preview_container:
                    ui.label("Sélectionnez un document dans la file.").classes("text-grey-6 q-pa-lg")
            if safe_clear(form_container):
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
        if job.analysis is None:
            ui.notify("Analyse manquante.", type="warning")
            return

        try:
            document_summary = str(form_refs.get("document_summary").value or "").strip()
            validations: list[TaskValidationInput] = []
            original_tasks = job.analysis.tasks

            for idx, task in enumerate(original_tasks):
                if idx in job.excluded_task_indices:
                    continue
                card_key = f"{job_id}_{idx}"
                title = str(form_refs[f"{card_key}_title"].value or "").strip()
                date_emission = parse_optional_date(
                    str(form_refs[f"{card_key}_date_emission"].value)
                )
                if date_emission is None:
                    raise ValueError(f"La date d'émission est obligatoire (fiche {idx + 1}).")
                date_event = parse_optional_date(str(form_refs[f"{card_key}_date_event"].value))
                deadline = parse_optional_date(str(form_refs[f"{card_key}_deadline"].value))
                category = str(form_refs[f"{card_key}_category"].value)
                tags = parse_tags_input(str(form_refs[f"{card_key}_tags"].value or ""))
                suggestion = str(form_refs[f"{card_key}_suggestion"].value or "").strip() or None

                validations.append(
                    TaskValidationInput(
                        title=title,
                        date_emission=date_emission,
                        date_event=date_event,
                        deadline=deadline,
                        category=category,
                        tags=tags,
                        raw_summary=document_summary,
                        justification_proof=task.justification_proof,
                        suggestion=suggestion or task.suggestion,
                    )
                )

            if not validations:
                ui.notify("Sélectionnez au moins une fiche à valider.", type="warning")
                return

            ged_date = min(item.date_emission for item in validations)
            ged_category = validations[0].category
            if all(item.category == "perso" for item in validations):
                ged_category = "perso"
            elif all(item.category == "pro" for item in validations):
                ged_category = "pro"
            ged_title = validations[0].title if len(validations) == 1 else _display_filename(
                job.file_path
            ).rsplit(".", 1)[0]

            task_ids = validate_inbox_tasks(
                job.file_path,
                validations,
                ged_title=ged_title,
                ged_category=ged_category,
                ged_date_emission=ged_date,
                document_summary=document_summary,
            )
            ui.notify(
                f"Document classé — {len(task_ids)} tâche(s) créée(s).",
                type="positive",
            )
            for task_id in task_ids:
                if try_auto_sync_task(task_id):
                    ui.notify(
                        f"Tâche #{task_id} synchronisée avec Google Calendar.",
                        type="positive",
                    )
            remove_job(job_id)
        except Exception as exc:
            logger.exception("Validation échouée")
            ui.notify(f"Erreur lors de la validation : {exc}", type="negative")

    def on_queue_changed() -> None:
        def _refresh_ui() -> None:
            if not element_client_alive(form_container):
                _detach_queue_listener()
                return
            render_queue.refresh()
            update_queue_badge()
            if state.active_job_id:
                job = queue.get_job(state.active_job_id)
                if job:
                    render_form_for_job(job)

        try:
            run_if_client_alive(form_container, _refresh_ui, on_dead=_detach_queue_listener)
        except RuntimeError:
            _detach_queue_listener()

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
    wire_clipboard_paste(upload, paste_zone)

    ui.timer(2.0, refresh_mock_banner, once=True)

    queue.add_listener(on_queue_changed)
    try:
        form_container.client.on_disconnect(_detach_queue_listener)
    except RuntimeError:
        logger.debug("Impossible d'enregistrer on_disconnect sur l'Inbox.")
    render_queue()
    update_queue_badge()

    def refresh_inbox() -> None:
        def _do_refresh() -> None:
            render_queue.refresh()
            update_queue_badge()
            refresh_mock_banner()
            if state.active_job_id:
                job = queue.get_job(state.active_job_id)
                if job:
                    render_preview(job.file_path)
                    render_form_for_job(job)

        run_if_client_alive(form_container, _do_refresh, on_dead=_detach_queue_listener)

    register_tab_refresh("inbox", refresh_inbox)
    return refresh_inbox
