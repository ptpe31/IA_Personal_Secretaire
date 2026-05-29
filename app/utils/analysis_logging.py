"""Logs structurés pour le suivi des analyses document → tâches."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.analysis import DocumentAnalysisResult, TaskAnalysisItem
    from app.services.task_service import TaskValidationInput

_SEPARATOR = "=" * 72
_SUB_SEPARATOR = "-" * 72


def _fmt_date(value) -> str:
    if value is None:
        return "—"
    return str(value)


def format_task_analysis_item(task: TaskAnalysisItem, *, index: int, total: int) -> str:
    lines = [
        f"  Tâche {index}/{total}",
        f"    titre              : {task.title}",
        f"    date_emission      : {_fmt_date(task.date_emission)}",
        f"    date_event         : {_fmt_date(task.date_event)}",
        f"    deadline           : {_fmt_date(task.deadline)}",
        f"    category           : {task.category}",
        f"    tags               : {', '.join(task.tags) if task.tags else '—'}",
        f"    confidence         : {task.confidence:.0%}",
        f"    justification_proof: {task.justification_proof}",
        f"    suggestion         : {task.suggestion or '—'}",
    ]
    return "\n".join(lines)


def format_validation_item(item: TaskValidationInput, *, index: int, total: int) -> str:
    lines = [
        f"  Tâche validée {index}/{total}",
        f"    titre              : {item.title}",
        f"    date_emission      : {_fmt_date(item.date_emission)}",
        f"    date_event         : {_fmt_date(item.date_event)}",
        f"    deadline           : {_fmt_date(item.deadline)}",
        f"    category           : {item.category}",
        f"    tags               : {', '.join(item.tags) if item.tags else '—'}",
        f"    justification_proof: {item.justification_proof or '—'}",
        f"    suggestion         : {item.suggestion or '—'}",
    ]
    return "\n".join(lines)


def log_analysis_result(
    logger: logging.Logger,
    *,
    stage: str,
    filename: str,
    result: DocumentAnalysisResult,
    extra: str | None = None,
) -> None:
    """Affiche le détail complet d'une analyse IA pour un document."""
    task_blocks = [
        format_task_analysis_item(task, index=index, total=len(result.tasks))
        for index, task in enumerate(result.tasks, start=1)
    ]
    body = "\n".join(
        [
            _SEPARATOR,
            f"[ANALYSE — {stage}] Document : {filename}",
            _SUB_SEPARATOR,
            f"  document_summary   : {result.document_summary or '—'}",
            f"  confidence globale : {result.confidence:.0%}",
            f"  nombre de tâches   : {len(result.tasks)}",
        ]
    )
    if extra:
        body += f"\n  note               : {extra}"
    if task_blocks:
        body += "\n" + _SUB_SEPARATOR + "\n" + "\n".join(task_blocks)
    body += f"\n{_SEPARATOR}"
    logger.info("\n%s", body)


def log_tasks_validated(
    logger: logging.Logger,
    *,
    filename: str,
    document_id: int,
    ged_path: str,
    document_summary: str,
    tasks: list[TaskValidationInput],
    task_ids: list[int],
) -> None:
    """Affiche le détail des tâches persistées en base pour un document."""
    task_blocks = [
        format_validation_item(item, index=index, total=len(tasks))
        + f"\n    → task_id en base  : {task_ids[index - 1]}"
        for index, item in enumerate(tasks, start=1)
    ]
    body = "\n".join(
        [
            _SEPARATOR,
            f"[VALIDATION INBOX] Document : {filename}",
            _SUB_SEPARATOR,
            f"  document_id        : {document_id}",
            f"  chemin GED         : {ged_path}",
            f"  document_summary   : {document_summary or '—'}",
            f"  tâches créées      : {len(task_ids)}",
            _SUB_SEPARATOR,
            *task_blocks,
            _SEPARATOR,
        ]
    )
    logger.info("\n%s", body)
