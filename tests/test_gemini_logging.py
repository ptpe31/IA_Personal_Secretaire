"""Tests logs Gemini."""

from unittest.mock import MagicMock, patch

from app.services.gemini_client import USER_PROMPT, _log_gemini_request


def test_log_gemini_request_includes_full_prompts(caplog):
    caplog.set_level("INFO")
    system = "Tu es un assistant.\nAncrage 2026."
    _log_gemini_request(
        filename="doc.png",
        model_name="gemini-2.5-flash",
        api_key="AIzaSy1234567890abcd",
        mime_type="image/png",
        image_size=12345,
        system_prompt=system,
    )
    text = caplog.text
    assert system in text
    assert USER_PROMPT in text
    assert "system_instruction" in text
    assert "gemini-2.5-flash" in text


def test_gemini_client_logs_prompt_on_analyze(tmp_path, monkeypatch, caplog):
    caplog.set_level("INFO")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy1234567890abcd")
    sample = tmp_path / "doc.png"
    sample.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    payload = {
        "tasks": [
            {
                "title": "Test",
                "date_emission": "2026-05-12",
                "category": "pro",
                "tags": ["test"],
                "justification_proof": "Aucune",
            }
        ],
        "document_summary": "Test",
        "confidence": 0.9,
    }

    mock_response = MagicMock()
    mock_response.text = __import__("json").dumps(payload)
    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response
    mock_client = MagicMock()
    mock_client.models = mock_models

    with patch("google.genai.Client", return_value=mock_client), patch(
        "app.services.gemini_client.load_image_bytes_for_vision",
        return_value=b"png-bytes",
    ):
        from app.services.gemini_client import GeminiClient

        GeminiClient().analyze_document(sample)

    assert "system_instruction" in caplog.text
    assert USER_PROMPT in caplog.text
