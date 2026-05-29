"""Tests unitaires fondations."""

from datetime import date

import pytest

from app.models.analysis import (
    DocumentAnalysis,
    DocumentAnalysisResult,
    TaskAnalysisItem,
    normalize_analysis_payload,
)
from app.services.mock_ollama_client import MockOllamaClient
from app.utils.tags import normalize_tags


def test_task_analysis_item_validates_json():
    data = {
        "title": "Mettre à jour Expo",
        "date_emission": "2026-05-28",
        "date_event": None,
        "deadline": "2026-06-26",
        "category": "pro",
        "tags": ["Tech", "Expo"],
        "confidence": 0.85,
        "justification_proof": "deadline SDK Expo le 26 juin 2026",
    }
    analysis = TaskAnalysisItem.model_validate(data)
    assert analysis.title == "Mettre à jour Expo"
    assert analysis.date_emission == date(2026, 5, 28)
    assert analysis.tags == ["tech", "expo"]


def test_task_analysis_accepts_string_null_from_llm():
    """Ollama renvoie parfois la chaîne 'null' au lieu de null JSON."""
    data = {
        "title": "Maintenance Expo",
        "date_emission": "2026-05-28",
        "date_event": "null",
        "deadline": "null",
        "category": "pro",
        "tags": ["Tech"],
        "confidence": 0.7,
        "justification_proof": "Aucune",
    }
    analysis = TaskAnalysisItem.model_validate(data)
    assert analysis.date_event is None
    assert analysis.deadline is None


def test_document_analysis_result_multi_tasks():
    payload = normalize_analysis_payload(
        {
            "tasks": [
                {
                    "title": "Répétition 1",
                    "date_emission": "2026-05-26",
                    "deadline": "2026-06-04",
                    "category": "perso",
                    "tags": ["danse"],
                    "justification_proof": "le 4 juin",
                },
                {
                    "title": "Spectacle",
                    "date_emission": "2026-05-26",
                    "deadline": "2026-06-27",
                    "category": "perso",
                    "tags": ["spectacle"],
                    "justification_proof": "27 juin 2026",
                },
            ],
            "document_summary": "Mail hip-hop",
            "confidence": 0.8,
        }
    )
    result = DocumentAnalysisResult.model_validate(payload)
    assert len(result.tasks) == 2


def test_normalize_analysis_payload_legacy_single_task():
    legacy = {
        "title": "Mettre à jour Expo",
        "date_emission": "2026-05-28",
        "date_event": None,
        "deadline": "2026-06-26",
        "category": "pro",
        "tags": ["Tech", "Expo"],
        "confidence": 0.85,
        "raw_summary": "Mail maintenance Expo.",
    }
    payload = normalize_analysis_payload(legacy)
    result = DocumentAnalysisResult.model_validate(payload)
    assert len(result.tasks) == 1
    assert result.tasks[0].title == "Mettre à jour Expo"
    assert result.document_summary == "Mail maintenance Expo."


def test_normalize_tags_cleans_corrupted_accents():
    assert normalize_tags(["re´pétition de danse"]) == ["repetition", "danse"]


def test_mock_client_returns_valid_analysis(tmp_path):
    sample = tmp_path / "expo_screenshot.png"
    sample.write_bytes(b"fake")
    client = MockOllamaClient()
    result = client.analyze_document(sample)
    assert len(result.tasks) >= 1
    assert result.tasks[0].title
    assert result.tasks[0].category in ("pro", "perso")
    assert client.is_mock is True


def test_mock_client_hiphop_pack(tmp_path):
    sample = tmp_path / "mail_hiphop_culture.png"
    sample.write_bytes(b"fake")
    client = MockOllamaClient()
    result = client.analyze_document(sample)
    assert len(result.tasks) == 5
    assert result.tasks[-1].title.startswith("Spectacle")


def test_document_analysis_alias():
    item = DocumentAnalysis.model_validate(
        {
            "title": "Test",
            "date_emission": "2026-05-29",
            "category": "pro",
            "tags": [],
        }
    )
    assert item.title == "Test"
