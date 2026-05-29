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

from app.models.analysis import DocumentAnalysis
from app.services.ollama_client import AnalysisClient, get_analysis_client

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
    analysis: DocumentAnalysis | None = None
    error: str | None = None


class InboxQueueService:
    """File FIFO serialisée pour les analyses Ollama."""

    def __init__(self) -> None:
        self._jobs: dict[str, InboxJob] = {}
        self._order: list[str] = []
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._listeners: list[Listener] = []
        self._worker_task: asyncio.Task | None = None
        self._client: AnalysisClient = get_analysis_client()

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

    def remove_job(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
        if job_id in self._order:
            self._order.remove(job_id)
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
                analysis = await asyncio.to_thread(self._client.analyze_document, job.file_path)
                job.analysis = analysis
                job.status = JobStatus.READY
                job.error = None
                logger.info("Analyse terminée — job %s (%s)", job_id, job.filename)
            except Exception as exc:
                logger.exception("Analyse échouée — job %s", job_id)
                job.status = JobStatus.FAILED
                job.error = str(exc)

            self._notify()
            self._queue.task_done()

            try:
                from nicegui import ui

                if job.status == JobStatus.READY:
                    title = job.analysis.title if job.analysis else job.filename
                    ui.notify(
                        f"Analyse terminée : « {title} » — ouvrez la file pour valider.",
                        type="positive",
                        timeout=8000,
                    )
                else:
                    ui.notify(
                        f"Échec analyse « {job.filename} » : {job.error}",
                        type="negative",
                        timeout=8000,
                    )
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
