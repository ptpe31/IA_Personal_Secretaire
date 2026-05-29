"""Post-traitement commun des réponses IA (Ollama / Gemini)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.models.analysis import DocumentAnalysisResult, normalize_analysis_payload
from app.services.task_expansion import expand_analysis_tasks
from app.utils.analysis_logging import log_analysis_result

logger = logging.getLogger(__name__)


def parse_json_content(content: str) -> dict:
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("Réponse IA sans JSON valide") from None
        return json.loads(match.group())


def sanitize_llm_payload(data: dict) -> dict:
    """Corrige les artefacts JSON fréquents des modèles."""
    cleaned = dict(data)

    if "tasks" in cleaned and isinstance(cleaned["tasks"], list):
        for task in cleaned["tasks"]:
            if not isinstance(task, dict):
                continue
            for key in ("date_event", "deadline", "date_emission", "suggestion"):
                value = task.get(key)
                if isinstance(value, str) and value.strip().lower() in (
                    "null",
                    "none",
                    "",
                    "n/a",
                ):
                    task[key] = None
    else:
        for key in ("date_event", "deadline", "date_emission"):
            value = cleaned.get(key)
            if isinstance(value, str) and value.strip().lower() in (
                "null",
                "none",
                "",
                "n/a",
            ):
                cleaned[key] = None

    if cleaned.get("document_summary") is None and cleaned.get("raw_summary") is None:
        cleaned["document_summary"] = ""
    return cleaned


def finalize_document_analysis(
    data: dict,
    *,
    file_path: Path,
    stage_prefix: str,
) -> DocumentAnalysisResult:
    """Normalise, valide, journalise et développe les tâches multi-dates."""
    data = sanitize_llm_payload(data)
    data = normalize_analysis_payload(data)
    result = DocumentAnalysisResult.model_validate(data)
    log_analysis_result(
        logger,
        stage=f"{stage_prefix} brut (avant expansion)",
        filename=file_path.name,
        result=result,
    )
    expanded = expand_analysis_tasks(result)
    if len(expanded.tasks) != len(result.tasks):
        log_analysis_result(
            logger,
            stage="POST-EXPANSION dates",
            filename=file_path.name,
            result=expanded,
            extra=f"{len(result.tasks)} → {len(expanded.tasks)} tâche(s)",
        )
    else:
        logger.info(
            "Analyse %s — expansion non appliquée (%s tâche(s))",
            file_path.name,
            len(expanded.tasks),
        )
    return expanded
