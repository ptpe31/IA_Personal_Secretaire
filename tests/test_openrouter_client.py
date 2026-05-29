"""Tests client et routage OpenRouter."""

from unittest.mock import MagicMock, patch

import httpx

from app.config import IA_PROVIDER_GEMINI, IA_PROVIDER_OPENROUTER
from app.services.analysis_client import get_analysis_client
from app.services.gemini_client import GeminiClient
from app.services.openrouter_client import OpenRouterClient


def test_describe_analysis_engine_openrouter():
    from app.services.analysis_client import describe_analysis_engine
    from app.services.openrouter_client import OpenRouterClient

    client = OpenRouterClient(api_key="k", model_name="qwen/qwen-2.5-vl-72b-instruct")
    assert describe_analysis_engine(client) == "OpenRouter (qwen/qwen-2.5-vl-72b-instruct)"


def test_describe_analysis_engine_gemini():
    from app.services.analysis_client import describe_analysis_engine
    from app.services.gemini_client import GeminiClient

    client = GeminiClient(api_key="k", model_name="gemini-2.5-flash")
    assert describe_analysis_engine(client) == "Gemini (gemini-2.5-flash)"


def test_get_analysis_client_uses_openrouter_when_selected(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
    with patch(
        "app.services.analysis_client.get_active_ia_provider",
        return_value=IA_PROVIDER_OPENROUTER,
    ):
        client = get_analysis_client()
    assert isinstance(client, OpenRouterClient)
    assert client.model_name == "qwen/qwen-2.5-vl-72b-instruct"


def test_get_analysis_client_openrouter_fallback_to_gemini(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    with patch(
        "app.services.analysis_client.get_active_ia_provider",
        return_value=IA_PROVIDER_OPENROUTER,
    ), patch("app.services.openrouter_client.get_openrouter_api_key", return_value=None):
        client = get_analysis_client()
    assert isinstance(client, GeminiClient)


def test_get_analysis_client_gemini_by_default(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    with patch(
        "app.services.analysis_client.get_active_ia_provider",
        return_value=IA_PROVIDER_GEMINI,
    ):
        client = get_analysis_client()
    assert isinstance(client, GeminiClient)


def test_openrouter_client_analyze_document(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
    sample = tmp_path / "doc.png"
    sample.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    payload = {
        "tasks": [
            {
                "title": "Réunion équipe",
                "date_emission": "2026-05-29",
                "date_event": "2026-06-05",
                "deadline": "2026-06-05",
                "category": "pro",
                "tags": ["reunion"],
                "justification_proof": "Réunion le 5 juin",
                "suggestion": "Préparer ordre du jour",
            }
        ],
        "document_summary": "Convocation",
        "confidence": 0.9,
    }

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": __import__("json").dumps(payload)}}]
    }

    with patch(
        "app.services.openrouter_client.load_image_bytes_for_vision",
        return_value=b"png-bytes",
    ), patch(
        "app.services.openrouter_client.httpx.post",
        return_value=mock_response,
    ) as mock_post:
        client = OpenRouterClient()
        result = client.analyze_document(sample)

    assert len(result.tasks) == 1
    assert result.tasks[0].title == "Réunion équipe"
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer or-test-key"
    assert call_kwargs["json"]["temperature"] == 0.0
    assert call_kwargs["json"]["model"] == "qwen/qwen-2.5-vl-72b-instruct"


def test_openrouter_client_raises_on_http_error(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
    sample = tmp_path / "doc.png"
    sample.write_bytes(b"\x89PNG\r\n\x1a\n")

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error",
        request=MagicMock(),
        response=MagicMock(status_code=401),
    )

    with patch(
        "app.services.openrouter_client.load_image_bytes_for_vision",
        return_value=b"png",
    ), patch("app.services.openrouter_client.httpx.post", return_value=mock_response):
        client = OpenRouterClient()
        try:
            client.analyze_document(sample)
            raised = False
        except httpx.HTTPStatusError:
            raised = True
    assert raised
