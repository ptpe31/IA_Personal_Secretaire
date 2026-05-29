"""Tests factory et client Gemini."""

from unittest.mock import MagicMock, patch

import google.generativeai as genai

from app.models.analysis import DocumentAnalysisResult
from app.services.analysis_client import get_analysis_client
from app.services.gemini_client import GeminiClient, gemini_response_schema
from app.services.mock_ollama_client import MockOllamaClient
from app.services.ollama_client import OllamaClient


def test_get_analysis_client_prefers_gemini_when_key_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = get_analysis_client()
    assert isinstance(client, GeminiClient)
    assert client.is_mock is False


def test_get_analysis_client_falls_back_to_ollama(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with patch("app.services.gemini_client.GeminiClient") as mock_gemini_cls:
        mock_gemini_cls.return_value.is_available.return_value = False
        with patch("app.services.ollama_client.OllamaClient") as mock_ollama_cls:
            mock_ollama_cls.return_value.is_available.return_value = True
            mock_ollama_cls.return_value.model = "llama3.2-vision"
            client = get_analysis_client()
    assert client is mock_ollama_cls.return_value


def test_get_analysis_client_falls_back_to_mock(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with patch("app.services.gemini_client.GeminiClient") as mock_gemini_cls:
        mock_gemini_cls.return_value.is_available.return_value = False
        with patch("app.services.ollama_client.OllamaClient") as mock_ollama_cls:
            mock_ollama_cls.return_value.is_available.return_value = False
            client = get_analysis_client()
    assert isinstance(client, MockOllamaClient)


def test_gemini_response_schema_strips_unsupported_keys():
    schema = gemini_response_schema(DocumentAnalysisResult)

    def walk(node):
        if isinstance(node, dict):
            for key in node:
                assert key not in {"minItems", "maxItems", "minLength", "maxLength"}
                walk(node[key])
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    assert schema["type"] == "object"
    assert "tasks" in schema["properties"]


def test_gemini_generation_config_accepts_sanitized_schema():
    config = genai.GenerationConfig(
        response_mime_type="application/json",
        response_schema=gemini_response_schema(DocumentAnalysisResult),
    )
    assert config.response_mime_type == "application/json"


def test_gemini_client_finalize_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    sample = tmp_path / "doc.png"
    sample.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    payload = {
        "tasks": [
            {
                "title": "Séance de formation (1/3)",
                "date_emission": "2026-05-12",
                "date_event": "2026-11-05",
                "deadline": "2026-11-05",
                "category": "pro",
                "tags": ["formation"],
                "justification_proof": "Séances de formation obligatoires les 5, 12 et 19 novembre",
                "suggestion": "Horaires : 14h à 16h",
            }
        ],
        "document_summary": "Mail formation",
        "confidence": 0.9,
    }

    mock_response = MagicMock()
    mock_response.text = __import__("json").dumps(payload)

    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    with patch("google.generativeai.configure"), patch(
        "google.generativeai.GenerativeModel", return_value=mock_model
    ), patch(
        "app.services.gemini_client.load_image_bytes_for_vision",
        return_value=b"png-bytes",
    ):
        client = GeminiClient(model_name="gemini-1.5-flash")
        result = client.analyze_document(sample)

    assert len(result.tasks) >= 1
    assert result.tasks[0].title.startswith("Séance de formation")
    mock_model.generate_content.assert_called_once()
