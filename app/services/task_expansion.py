"""Expansion des analyses sous-découpées (1 tâche au lieu de N dates)."""

from __future__ import annotations

import re

from app.models.analysis import DocumentAnalysisResult, TaskAnalysisItem
from app.utils.date_extraction import extract_french_event_dates


def expand_analysis_tasks(result: DocumentAnalysisResult) -> DocumentAnalysisResult:
    """
    Si l'IA n'a renvoyé qu'une tâche mais plusieurs dates sont visibles
    dans les preuves / le résumé, génère une fiche par date.
    """
    if len(result.tasks) != 1:
        return result

    task = result.tasks[0]
    blob = " ".join(
        part
        for part in (task.title, task.justification_proof, result.document_summary)
        if part and part != "Aucune"
    )
    if not blob.strip():
        return result

    default_year = task.date_emission.year
    events = extract_french_event_dates(blob, default_year=default_year)
    if len(events) <= 1:
        return result

    blob_lower = blob.lower()
    is_hiphop = any(k in blob_lower for k in ("hip", "hip-hop", "hip hop", "danse"))
    rehearsal_dates = [event for event in events if "spectacle" not in event[1].lower()]
    spectacle_dates = [event for event in events if "spectacle" in event[1].lower()]
    if not spectacle_dates:
        spectacle_dates = [
            event
            for event in events
            if event not in rehearsal_dates
            and any(k in event[1].lower() for k in ("astrolab", "représentation", "fin d'année"))
        ]
        rehearsal_dates = [event for event in events if event not in spectacle_dates]

    if not rehearsal_dates and len(events) > 1:
        rehearsal_dates = events[:-1]
        spectacle_dates = events[-1:]

    expanded: list[TaskAnalysisItem] = []
    rep_total = len(rehearsal_dates)
    rehearsal_suggestion = task.suggestion or infer_rehearsal_suggestion(blob)
    spectacle_suggestion = infer_spectacle_suggestion(blob) or task.suggestion

    for index, (event_date, snippet) in enumerate(rehearsal_dates, start=1):
        if is_hiphop and rep_total > 1:
            title = f"Répétition Hip-Hop {index}/{rep_total}"
        elif rep_total > 1:
            title = f"{task.title} ({index}/{rep_total})"
        else:
            title = task.title

        expanded.append(
            task.model_copy(
                update={
                    "title": title,
                    "date_event": event_date,
                    "deadline": event_date,
                    "justification_proof": snippet or task.justification_proof,
                    "suggestion": rehearsal_suggestion,
                }
            )
        )

    for event_date, snippet in spectacle_dates:
        title = (
            "Spectacle de fin d'année Hip-Hop"
            if is_hiphop
            else re.sub(r"\s*\(\d+/\d+\)\s*", " ", task.title).strip() or task.title
        )
        expanded.append(
            task.model_copy(
                update={
                    "title": title,
                    "date_event": event_date,
                    "deadline": event_date,
                    "justification_proof": snippet or task.justification_proof,
                    "tags": list(dict.fromkeys([*task.tags, "spectacle"])),
                    "suggestion": spectacle_suggestion,
                }
            )
        )

    if len(expanded) <= 1:
        return result

    return result.model_copy(update={"tasks": expanded})

from app.utils.suggestion_infer import infer_rehearsal_suggestion, infer_spectacle_suggestion
