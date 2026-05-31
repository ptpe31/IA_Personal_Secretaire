"""Tests get_drive_analysis_client."""

import pytest

from app.services.analysis_client import get_drive_analysis_client


def test_get_drive_analysis_client_raises_without_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setattr(
        "app.services.analysis_client.get_active_ia_provider",
        lambda: "Gemini (Natif)",
    )
    monkeypatch.setattr(
        "app.config.get_gemini_api_key",
        lambda: "",
    )
    monkeypatch.setattr(
        "app.config.get_openrouter_api_key",
        lambda: "",
    )
    with pytest.raises(RuntimeError, match="Aucun moteur IA cloud"):
        get_drive_analysis_client()


def test_get_drive_analysis_client_prefers_gemini(monkeypatch):
    monkeypatch.setattr(
        "app.services.analysis_client.get_active_ia_provider",
        lambda: "Gemini (Natif)",
    )
    monkeypatch.setattr(
        "app.services.gemini_client.get_gemini_api_key",
        lambda: "test-key",
    )
    client = get_drive_analysis_client()
    from app.services.gemini_client import GeminiClient

    assert isinstance(client, GeminiClient)
