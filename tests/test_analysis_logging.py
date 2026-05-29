"""Tests logs structurés analyse / validation."""

import logging

from app.models.analysis import DocumentAnalysisResult, TaskAnalysisItem
from app.services.task_service import TaskValidationInput
from app.utils.analysis_logging import log_analysis_result, log_tasks_validated
from datetime import date


def test_log_analysis_result(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test.analysis")
    result = DocumentAnalysisResult(
        tasks=[
            TaskAnalysisItem(
                title="Répétition Hip-Hop (1/4)",
                date_emission=date(2026, 5, 26),
                deadline=date(2026, 6, 4),
                category="perso",
                tags=["danse", "hiphop"],
                justification_proof="le 4 juin de 18h à 19h",
            )
        ],
        document_summary="Mail hip-hop",
        confidence=0.8,
    )
    log_analysis_result(logger, stage="TEST", filename="mail.png", result=result)
    assert "[ANALYSE — TEST]" in caplog.text
    assert "Répétition Hip-Hop (1/4)" in caplog.text
    assert "justification_proof" in caplog.text


def test_log_tasks_validated(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test.validation")
    tasks = [
        TaskValidationInput(
            title="Spectacle Hip-Hop",
            date_emission=date(2026, 5, 26),
            date_event=date(2026, 6, 27),
            deadline=date(2026, 6, 27),
            category="perso",
            tags=["spectacle"],
            raw_summary="Mail hip-hop",
            justification_proof="27 juin 2026",
        )
    ]
    log_tasks_validated(
        logger,
        filename="mail.png",
        document_id=42,
        ged_path="Perso/GED/2026-05-26_Mail.png",
        document_summary="Mail hip-hop",
        tasks=tasks,
        task_ids=[101],
    )
    assert "[VALIDATION INBOX]" in caplog.text
    assert "task_id en base  : 101" in caplog.text
