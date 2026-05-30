"""Tests recherche omnibox dashboard."""

from datetime import date

from app.models.task import TaskDTO
from app.services.task_service import matches_task_search, suggest_tags


def _task(**kwargs) -> TaskDTO:
    defaults = {
        "id": 1,
        "title": "Déclaration URSSAF",
        "category": "pro",
        "date_emission": date(2026, 5, 1),
        "date_event": None,
        "deadline": None,
        "status": "todo",
        "completed_at": None,
        "document_id": None,
        "raw_summary": None,
        "notes": None,
        "stored_path": None,
        "original_filename": None,
        "tags": ["urssaf", "compta"],
    }
    defaults.update(kwargs)
    return TaskDTO(**defaults)


def test_empty_query_matches_all():
    task = _task()
    assert matches_task_search("", task)
    assert matches_task_search("   ", task)


def test_matches_title():
    task = _task(title="Préparer le spectacle de fin d'année")
    assert matches_task_search("spectacle", task)
    assert matches_task_search("SPECTACLE", task)


def test_matches_tag_without_hash():
    task = _task(title="Déclaration", tags=["urssaf", "compta"])
    assert matches_task_search("urssaf", task)
    assert matches_task_search("compta", task)


def test_matches_hash_tag_prefix():
    task = _task(tags=["urssaf", "compta"])
    assert matches_task_search("#urssaf", task)
    assert matches_task_search("#UR", task)
    assert not matches_task_search("#tech", task)


def test_hash_only_requires_tags():
    assert matches_task_search("#", _task(tags=["a"]))
    assert not matches_task_search("#", _task(tags=[]))


def test_suggest_tags_prefix():
    all_tags = ["urssaf", "compta", "tech", "spectacle"]
    assert suggest_tags("ur", all_tags) == ["urssaf"]
    assert suggest_tags("#UR", all_tags) == ["urssaf"]


def test_suggest_tags_empty_prefix_returns_limited():
    all_tags = [f"tag{i}" for i in range(12)]
    assert len(suggest_tags("", all_tags, limit=8)) == 8
    assert suggest_tags("#", all_tags, limit=3) == ["tag0", "tag1", "tag2"]
