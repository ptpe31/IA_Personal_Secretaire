"""Tests récurrence virtuelle et enrichissement URL."""

from datetime import date

from app.models.analysis import TaskAnalysisItem
from app.services.task_service import (
    archive_task,
    create_manual_task,
    get_task_by_id,
    list_tasks,
    update_task,
)
from app.utils.frequence import calculer_prochaine_echeance


def test_calculer_prochaine_echeance_mensuelle():
    assert calculer_prochaine_echeance(date(2026, 5, 29), "mensuelle") == date(
        2026, 6, 29
    )


def test_calculer_prochaine_echeance_trimestrielle():
    assert calculer_prochaine_echeance(date(2026, 3, 15), "trimestrielle") == date(
        2026, 6, 15
    )


def test_calculer_prochaine_echeance_annuelle():
    assert calculer_prochaine_echeance(date(2026, 1, 10), "annuelle") == date(
        2027, 1, 10
    )


def test_virtual_recurrence_advances_same_row():
    task_id = create_manual_task(
        title="Déclaration URSSAF",
        category="pro",
        start_date=date(2026, 6, 10),
    )
    update_task(
        task_id,
        title="Déclaration URSSAF",
        date_emission=date(2026, 6, 1),
        date_event=date(2026, 6, 10),
        deadline=date(2026, 6, 10),
        category="pro",
        tags=[],
        frequence="mensuelle",
        source_url="https://www.autoentrepreneur.urssaf.fr",
    )
    before_count = len(list_tasks(include_archived=True))

    result = archive_task(task_id)
    assert result == task_id

    task = get_task_by_id(task_id)
    assert task is not None
    assert task.completed_at is None
    assert task.deadline == date(2026, 7, 10)
    assert task.frequence == "mensuelle"
    assert task.source_url == "https://www.autoentrepreneur.urssaf.fr"
    assert len(list_tasks(include_archived=True)) == before_count


def test_analysis_normalizes_frequence_and_url():
    item = TaskAnalysisItem(
        title="Cotisation",
        date_emission="2026-05-01",
        frequence="trimestriel",
        source_url="autoentrepreneur.urssaf.fr",
    )
    assert item.frequence == "trimestrielle"
    assert item.source_url == "https://autoentrepreneur.urssaf.fr"
