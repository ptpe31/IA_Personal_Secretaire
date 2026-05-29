"""Interface et factory pour les clients d'analyse documentaire."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from app.models.analysis import DocumentAnalysisResult

logger = logging.getLogger(__name__)


class AnalysisClient(ABC):
    """Interface commune Gemini / Ollama / Mock."""

    is_mock: bool = False

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def analyze_document(self, file_path: Path) -> DocumentAnalysisResult: ...

    @property
    def warning_message(self) -> str | None:
        return None


def get_analysis_client() -> AnalysisClient:
    """
    Retourne GeminiClient si une clé API est configurée,
    sinon OllamaClient si le modèle local est prêt,
    sinon MockOllamaClient.
    """
    from app.services.gemini_client import GeminiClient
    from app.services.mock_ollama_client import MockOllamaClient
    from app.services.ollama_client import OllamaClient

    gemini = GeminiClient()
    if gemini.is_available():
        logger.info("Gemini prêt — modèle %s", gemini.model_name)
        return gemini

    ollama = OllamaClient()
    if ollama.is_available():
        logger.info("Ollama prêt — modèle %s", ollama.model)
        return ollama

    logger.warning(
        "Bascule vers MockOllamaClient (Gemini non configuré, Ollama injoignable)."
    )
    return MockOllamaClient()
