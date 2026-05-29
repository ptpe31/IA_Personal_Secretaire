"""Tests file d'attente Inbox."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.analysis import DocumentAnalysis
from app.services.inbox_queue import InboxQueueService, JobStatus


@pytest.fixture
def queue_service(tmp_path: Path) -> InboxQueueService:
    service = InboxQueueService()
    mock_client = MagicMock()
    mock_client.analyze_document.return_value = DocumentAnalysis.model_validate(
        {
            "title": "Test doc",
            "date_emission": "2026-05-29",
            "date_event": None,
            "deadline": None,
            "category": "pro",
            "tags": ["Test"],
            "confidence": 0.5,
            "raw_summary": "Résumé test",
        }
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

    queue_service.start()
    await asyncio.sleep(0.05)

    updated = queue_service.get_job(job.id)
    assert updated is not None
    assert updated.status == JobStatus.READY
    assert updated.analysis is not None
    assert updated.analysis.title == "Test doc"
