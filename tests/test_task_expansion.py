"""Tests expansion multi-dates et extraction."""

from datetime import date

from app.models.analysis import DocumentAnalysisResult, TaskAnalysisItem
from app.services.task_expansion import expand_analysis_tasks
from app.utils.date_extraction import extract_french_event_dates


def test_extract_french_event_dates_list_and_single():
    text = (
        "répétitions les 4, 11, 18 et 25 juin de 18h à 19h. "
        "inscription par mail ou au 05.62.11.62.66. "
        "spectacle samedi 27 juin 2026 à l'Astrolab'"
    )
    events = extract_french_event_dates(text, default_year=2026)
    assert [event[0] for event in events] == [
        date(2026, 6, 4),
        date(2026, 6, 11),
        date(2026, 6, 18),
        date(2026, 6, 25),
        date(2026, 6, 27),
    ]


def test_expand_single_task_into_multiple_dates():
    result = DocumentAnalysisResult(
        tasks=[
            TaskAnalysisItem(
                title="Atelier danse",
                date_emission=date(2026, 5, 26),
                deadline=date(2026, 6, 4),
                category="perso",
                tags=["danse"],
                justification_proof=(
                    "les séances auront lieu les 4, 11, 18 et 25 juin de 18h à 19h. "
                    "inscription par mail ou au 05.62.11.62.66. "
                    "spectacle samedi 27 juin 2026 à l'Astrolab'"
                ),
            )
        ],
        document_summary="Mail association culturelle",
        confidence=0.7,
    )

    expanded = expand_analysis_tasks(result)
    assert len(expanded.tasks) == 5
    assert expanded.tasks[0].suggestion == "Horaires de l'atelier : 18h à 19h"
    assert "inscription" in (expanded.tasks[-1].suggestion or "").lower()
    assert expanded.tasks[0].title == "Atelier danse (1/4)"
    assert expanded.tasks[-1].deadline == date(2026, 6, 27)
