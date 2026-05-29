"""Tests unitaires fondations."""

from datetime import date

import pytest

from app.models.analysis import DocumentAnalysis
from app.services.mock_ollama_client import MockOllamaClient


def test_document_analysis_validates_json():
    data = {
        "title": "Mettre à jour Expo",
        "date_emission": "2026-05-28",
        "date_event": None,
        "deadline": "2026-06-26",
        "category": "pro",
        "tags": ["Tech", "Expo"],
        "confidence": 0.85,
        "raw_summary": "Mail maintenance Expo.",
    }
    analysis = DocumentAnalysis.model_validate(data)
    assert analysis.title == "Mettre à jour Expo"
    assert analysis.date_emission == date(2026, 5, 28)


def test_mock_client_returns_valid_analysis(tmp_path):
    sample = tmp_path / "expo_screenshot.png"
    sample.write_bytes(b"fake")
    client = MockOllamaClient()
    result = client.analyze_document(sample)
    assert result.title
    assert result.category in ("pro", "perso")
    assert client.is_mock is True
