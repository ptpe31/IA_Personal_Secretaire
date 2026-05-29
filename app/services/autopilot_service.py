"""Validation automatique (mode Autopilote) des documents analysés."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.db.connection import get_setting
from app.models.analysis import DocumentAnalysisResult, TaskAnalysisItem
from app.services.calendar_service import try_auto_sync_task
from app.services.inbox_queue import InboxJob
from app.services.task_service import TaskValidationInput, validate_inbox_tasks


def is_autopilot_enabled() -> bool:
    return get_setting("autopilot_enabled", "true") == "true"


def display_filename(path: Path) -> str:
    name = path.name
    prefix, _, rest = name.partition("_")
    if len(prefix) == 32 and rest:
        return rest
    return name


def validations_from_analysis(
    analysis: DocumentAnalysisResult,
    *,
    file_path: Path,
    excluded_indices: set[int] | None = None,
) -> list[TaskValidationInput]:
    """Construit les tâches à persister à partir du résultat Ollama."""
    excluded = excluded_indices or set()
    document_summary = (analysis.document_summary or "").strip()
    validations: list[TaskValidationInput] = []

    for idx, task in enumerate(analysis.tasks):
        if idx in excluded:
            continue
        validations.append(_task_to_validation(task, document_summary=document_summary))

    if not validations:
        raise ValueError("Aucune tâche à valider.")

    return validations


def _task_to_validation(task: TaskAnalysisItem, *, document_summary: str) -> TaskValidationInput:
    return TaskValidationInput(
        title=task.title.strip(),
        date_emission=task.date_emission,
        date_event=task.date_event,
        deadline=task.deadline,
        category=task.category,
        tags=list(task.tags),
        raw_summary=document_summary,
        justification_proof=task.justification_proof,
        suggestion=task.suggestion,
    )


def _ged_params(
    validations: list[TaskValidationInput],
    file_path: Path,
) -> tuple[str, str, date]:
    ged_date = min(item.date_emission for item in validations)
    ged_category = validations[0].category
    if all(item.category == "perso" for item in validations):
        ged_category = "perso"
    elif all(item.category == "pro" for item in validations):
        ged_category = "pro"
    ged_title = (
        validations[0].title
        if len(validations) == 1
        else display_filename(file_path).rsplit(".", 1)[0]
    )
    return ged_title, ged_category, ged_date


def auto_validate_job(job: InboxJob) -> list[int]:
    """Valide automatiquement un job analysé (Autopilote)."""
    if job.analysis is None:
        raise ValueError("Analyse manquante.")

    validations = validations_from_analysis(
        job.analysis,
        file_path=job.file_path,
        excluded_indices=job.excluded_task_indices,
    )
    ged_title, ged_category, ged_date = _ged_params(validations, job.file_path)
    document_summary = (job.analysis.document_summary or "").strip()

    task_ids = validate_inbox_tasks(
        job.file_path,
        validations,
        ged_title=ged_title,
        ged_category=ged_category,
        ged_date_emission=ged_date,
        document_summary=document_summary,
    )
    for task_id in task_ids:
        try_auto_sync_task(task_id)
    return task_ids
