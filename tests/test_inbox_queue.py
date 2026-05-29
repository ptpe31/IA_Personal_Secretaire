"""Tests file d'attente Inbox."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.analysis import DocumentAnalysisResult, TaskAnalysisItem
from app.services.inbox_queue import InboxQueueService, JobStatus


@pytest.fixture
def queue_service(tmp_path: Path) -> InboxQueueService:
    service = InboxQueueService()
    mock_client = MagicMock()
    mock_client.analyze_document.return_value = DocumentAnalysisResult(
        tasks=[
            TaskAnalysisItem(
                title="Test doc",
                date_emission=__import__("datetime").date(2026, 5, 29),
                category="pro",
                tags=["test"],
                confidence=0.5,
                justification_proof="Aucune",
            )
        ],
        document_summary="Résumé test",
        confidence=0.5,
    )
    service._client = mock_client
    return service


def test_enqueue_assigns_queued_status(queue_service: InboxQueueService, tmp_path: Path):
    sample = tmp_path / "doc.png"
    sample.write_bytes(b"fake")
    job = queue_service.enqueue(sample, "doc.png", source="upload")
    assert job.status == JobStatus.QUEUED
    assert queue_service.queue_position(job.id) == 1


@pytest.mark.asyncio
async def test_worker_processes_job_to_ready(queue_service: InboxQueueService, tmp_path: Path):
    sample = tmp_path / "doc.png"
    sample.write_bytes(b"fake")
    job = queue_service.enqueue(sample, "doc.png")

    with patch("app.services.autopilot_service.is_autopilot_enabled", return_value=False):
        queue_service.start()
        await asyncio.sleep(0.05)

    updated = queue_service.get_job(job.id)
    assert updated is not None
    assert updated.status == JobStatus.READY
    assert updated.analysis is not None
    assert updated.analysis.tasks[0].title == "Test doc"


def test_manual_pending_count(queue_service: InboxQueueService, tmp_path: Path):
    sample = tmp_path / "doc.png"
    sample.write_bytes(b"fake")
    job = queue_service.enqueue(sample, "doc.png")
    assert queue_service.manual_pending_count() == 0
    assert queue_service.active_processing_job() is not None

    job.status = JobStatus.READY
    assert queue_service.manual_pending_count() == 1
    assert queue_service.failed_analysis_count() == 0
    assert queue_service.active_processing_job() is None

    job.status = JobStatus.FAILED
    assert queue_service.manual_pending_count() == 0
    assert queue_service.failed_analysis_count() == 1
