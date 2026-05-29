"""File d'attente d'analyse Inbox — traitement Ollama en arrière-plan."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from app.models.analysis import DocumentAnalysisResult
from app.utils.analysis_logging import log_analysis_result
from app.services.analysis_client import AnalysisClient, get_analysis_client

logger = logging.getLogger(__name__)

Listener = Callable[[], None]


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class InboxJob:
    id: str
    file_path: Path
    filename: str
    source: str
    status: JobStatus
    created_at: datetime = field(default_factory=datetime.now)
    analysis: DocumentAnalysisResult | None = None
    error: str | None = None
    excluded_task_indices: set[int] = field(default_factory=set)


class InboxQueueService:
    """File FIFO serialisée pour les analyses Ollama."""

    def __init__(self) -> None:
        self._jobs: dict[str, InboxJob] = {}
        self._order: list[str] = []
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._listeners: list[Listener] = []
        self._worker_task: asyncio.Task | None = None
        self._client: AnalysisClient | None = None

    @property
    def client(self) -> AnalysisClient:
        if self._client is None:
            self._client = get_analysis_client()
        return self._client

    def add_listener(self, listener: Listener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except RuntimeError as exc:
                if "client this element belongs to has been deleted" in str(exc).lower():
                    logger.debug("Listener Inbox ignoré — client NiceGUI déconnecté.")
                    self._listeners.remove(listener)
                else:
                    raise
            except Exception:
                logger.exception("Listener file Inbox en erreur")

    def start(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Worker file Inbox démarré.")

    def enqueue(self, file_path: Path, filename: str, *, source: str = "upload") -> InboxJob:
        job_id = uuid.uuid4().hex
        job = InboxJob(
            id=job_id,
            file_path=file_path,
            filename=filename,
            source=source,
            status=JobStatus.QUEUED,
        )
        self._jobs[job_id] = job
        self._order.append(job_id)
        self._queue.put_nowait(job_id)
        self._notify()
        return job

    def list_jobs(self) -> list[InboxJob]:
        return [self._jobs[jid] for jid in self._order if jid in self._jobs]

    def get_job(self, job_id: str) -> InboxJob | None:
        return self._jobs.get(job_id)

    def queue_position(self, job_id: str) -> int:
        waiting = [j for j in self.list_jobs() if j.status in (JobStatus.QUEUED, JobStatus.PROCESSING)]
        for index, job in enumerate(waiting, start=1):
            if job.id == job_id:
                return index
        return 0

    def pending_count(self) -> int:
        return sum(
            1 for job in self.list_jobs() if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING)
        )

    def manual_pending_count(self) -> int:
        """Documents en attente de validation manuelle (Inbox)."""
        return sum(
            1 for job in self.list_jobs() if job.status in (JobStatus.READY, JobStatus.FAILED)
        )

    def active_processing_job(self) -> InboxJob | None:
        """Premier job en file ou en cours d'analyse."""
        for job in self.list_jobs():
            if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
                return job
        return None

    def remove_job(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
        if job_id in self._order:
            self._order.remove(job_id)
        self._notify()

    def clear_all_jobs(self) -> None:
        """Réinitialise la file d'analyse en mémoire."""
        self._jobs.clear()
        self._order.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break
        self._notify()

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            job = self._jobs.get(job_id)
            if job is None:
                self._queue.task_done()
                continue

            job.status = JobStatus.PROCESSING
            self._notify()

            try:
                analysis = await asyncio.to_thread(self.client.analyze_document, job.file_path)
                job.analysis = analysis
                job.status = JobStatus.READY
                job.error = None
                log_analysis_result(
                    logger,
                    stage="FILE INBOX prête",
                    filename=job.filename,
                    result=analysis,
                    extra=f"job_id={job_id}",
                )
            except Exception as exc:
                logger.exception("Analyse échouée — job %s", job_id)
                job.status = JobStatus.FAILED
                job.error = str(exc)

            autopilot_done = False
            if job.status == JobStatus.READY:
                from app.services.autopilot_service import auto_validate_job, is_autopilot_enabled

                if is_autopilot_enabled():
                    try:
                        task_ids = await asyncio.to_thread(auto_validate_job, job)
                        logger.info(
                            "Autopilote — %s tâche(s) créée(s) pour « %s »",
                            len(task_ids),
                            job.filename,
                        )
                        self.remove_job(job_id)
                        autopilot_done = True
                        self._notify()
                        self._queue.task_done()
                        try:
                            from nicegui import ui

                            ui.notify(
                                f"Autopilote — {len(task_ids)} tâche(s) classée(s) "
                                f"pour « {job.filename} ».",
                                type="positive",
                                timeout=6000,
                            )
                        except RuntimeError:
                            pass
                        continue
                    except Exception as exc:
                        logger.exception("Autopilote échoué — job %s", job_id)
                        job.error = f"Validation automatique échouée : {exc}"

            self._notify()
            self._queue.task_done()

            if autopilot_done:
                continue

            try:
                from nicegui import ui

                if job.status == JobStatus.READY:
                    count = len(job.analysis.tasks) if job.analysis else 0
                    ui.notify(
                        f"Analyse terminée — {count} tâche(s) à valider dans l'Inbox "
                        f"pour « {job.filename} ».",
                        type="warning",
                        timeout=8000,
                    )
                elif job.status == JobStatus.FAILED:
                    ui.notify(
                        f"Échec analyse « {job.filename} » — validation manuelle requise.",
                        type="negative",
                        timeout=8000,
                    )
            except RuntimeError:
                logger.debug("Notification ignorée — aucun client NiceGUI actif.")
            except Exception:
                pass


_queue: InboxQueueService | None = None


def get_inbox_queue() -> InboxQueueService:
    global _queue
    if _queue is None:
        _queue = InboxQueueService()
    return _queue


def register_inbox_queue_startup() -> None:
    """Démarre le worker au lancement NiceGUI."""
    from nicegui import app

    @app.on_startup
    async def _start_inbox_worker() -> None:
        get_inbox_queue().start()
