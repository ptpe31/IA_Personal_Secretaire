"""Zone de dépôt de documents partagée (Dashboard & Inbox)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from pathlib import Path

from nicegui import events, ui

from app.config import INBOX_PATH
from app.services.inbox_ingest import extension_from_filename
from app.services.inbox_queue import InboxJob, get_inbox_queue
from app.utils.file_preview import is_allowed_extension

logger = logging.getLogger(__name__)

ACCEPT_MIME = ".pdf,.png,.jpg,.jpeg,.webp,.heic"


def create_paste_zone() -> ui.card:
    """Carte « Coller une image » activable au clic / focus."""
    with ui.card().classes(
        "w-full q-pa-md trankil-paste-zone cursor-pointer"
    ).props("flat bordered tabindex=0") as paste_zone:
        with ui.row().classes("items-center q-gutter-sm"):
            ui.icon("content_paste", size="md").classes("text-primary")
            with ui.column():
                ui.label("Coller une capture ou une image").classes("text-subtitle2")
                ui.label("Cliquez ici, puis ⌘V (Mac) ou Ctrl+V").classes(
                    "text-caption text-grey-7"
                )
    return paste_zone


def wire_clipboard_paste(upload: ui.upload, paste_zone: ui.element) -> None:
    """Branche le collage presse-papiers sur un ui.upload cible."""

    def activate_paste_zone() -> None:
        url = upload._props.get("url", "")
        ui.run_javascript(
            f"""
            window.__trankilPasteActive = true;
            window.__trankilUploadUrl = {json.dumps(url)};
            """
        )

    def deactivate_paste_zone() -> None:
        ui.run_javascript("window.__trankilPasteActive = false")

    paste_zone.on("click", activate_paste_zone)
    paste_zone.on("focus", activate_paste_zone)
    paste_zone.on("focusin", activate_paste_zone)
    paste_zone.on("focusout", deactivate_paste_zone)

    async def setup_clipboard_paste() -> None:
        await ui.run_javascript(
            """
            (function() {
                if (window.__trankilPasteListenerSetup) return;
                window.__trankilPasteListenerSetup = true;
                window.__trankilPasteActive = false;
                window.__trankilUploadUrl = '';

                document.addEventListener('paste', async (event) => {
                    if (!window.__trankilPasteActive || !window.__trankilUploadUrl) return;
                    const items = event.clipboardData?.items;
                    if (!items) return;

                    for (const item of items) {
                        if (!item.type.startsWith('image/')) continue;
                        event.preventDefault();

                        const blob = item.getAsFile();
                        if (!blob) continue;

                        const ext = item.type === 'image/jpeg' ? 'jpg'
                            : item.type === 'image/png' ? 'png'
                            : item.type === 'image/webp' ? 'webp'
                            : 'png';
                        const form = new FormData();
                        form.append('file', blob, `paste_${Date.now()}.${ext}`);

                        try {
                            await fetch(window.__trankilUploadUrl, {
                                method: 'POST',
                                body: form,
                            });
                        } catch (error) {
                            console.error('Trankil paste error', error);
                        }
                        break;
                    }
                });
            })();
            """
        )

    ui.timer(0.2, setup_clipboard_paste, once=True)


def create_document_upload(
    *,
    on_enqueued: Callable[[InboxJob], None] | None = None,
    compact: bool = False,
) -> ui.upload:
    """Crée un ui.upload branché sur la file d'analyse."""
    queue = get_inbox_queue()

    label = (
        "Glisser-déposer ou choisir (PDF, PNG, JPG, HEIC)"
        if compact
        else "Choisir ou déposer un document (PDF, PNG, JPG, HEIC)"
    )
    upload = ui.upload(
        label=label,
        auto_upload=True,
        max_files=1,
    ).props(f'accept="{ACCEPT_MIME}" bordered flat').classes("w-full")

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
            logger.exception("Erreur sauvegarde document")
            ui.notify(f"Erreur lors de la sauvegarde : {exc}", type="negative")
            return

        source = "paste" if filename.startswith("paste_") else "upload"
        job = queue.enqueue(dest, filename, source=source)
        upload.reset()
        if on_enqueued:
            on_enqueued(job)

    upload.on_upload(process_upload)
    return upload


def create_document_intake(
    *,
    side_by_side: bool = False,
    triple_column: bool = False,
    compact: bool = False,
    on_enqueued: Callable[[InboxJob], None] | None = None,
    third_column: Callable[[], None] | None = None,
) -> ui.upload:
    """Dépôt complet : collage presse-papiers + glisser-déposer (+ colonne optionnelle)."""
    if triple_column and third_column:
        with ui.row().classes("w-full q-col-gutter-md items-stretch"):
            with ui.column().classes("col flex"):
                paste_zone = create_paste_zone()
                paste_zone.classes(add="full-height flex flex-center")
            with ui.column().classes("col flex"):
                with ui.card().classes("w-full full-height q-pa-md").props("flat bordered"):
                    ui.label("Glisser-déposer un fichier").classes("text-subtitle2 q-mb-sm")
                    upload = create_document_upload(compact=compact, on_enqueued=on_enqueued)
            with ui.column().classes("col flex"):
                third_column()
    elif side_by_side:
        with ui.row().classes("w-full q-col-gutter-md items-stretch"):
            with ui.column().classes("col flex"):
                paste_zone = create_paste_zone()
                paste_zone.classes(add="full-height flex flex-center")
            with ui.column().classes("col flex"):
                with ui.card().classes("w-full full-height q-pa-md").props("flat bordered"):
                    ui.label("Glisser-déposer un fichier").classes("text-subtitle2 q-mb-sm")
                    upload = create_document_upload(compact=compact, on_enqueued=on_enqueued)
    else:
        paste_zone = create_paste_zone()
        upload = create_document_upload(compact=compact, on_enqueued=on_enqueued)

    wire_clipboard_paste(upload, paste_zone)
    return upload
