"""Interface et factory pour les clients d'analyse documentaire."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import IA_PROVIDER_OPENROUTER, get_active_ia_provider
from app.models.analysis import DocumentAnalysisResult

logger = logging.getLogger(__name__)


class AnalysisClient(ABC):
    """Interface commune Gemini / OpenRouter / Ollama / Mock."""

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
    Retourne le client selon ``active_ia_provider`` (settings) :
    OpenRouter (Éco) → Gemini → Ollama → Mock.
    """
    from app.services.gemini_client import GeminiClient
    from app.services.mock_ollama_client import MockOllamaClient
    from app.services.ollama_client import OllamaClient
    from app.services.openrouter_client import OpenRouterClient

    provider = get_active_ia_provider()

    if provider == IA_PROVIDER_OPENROUTER:
        openrouter = OpenRouterClient()
        if openrouter.is_available():
            logger.info("OpenRouter prêt — modèle %s", openrouter.model_name)
            return openrouter
        logger.warning(
            "OpenRouter (Éco) sélectionné mais clé absente — repli sur Gemini."
        )

    gemini = GeminiClient()
    if gemini.is_available():
        logger.info("Gemini prêt — modèle %s", gemini.model_name)
        return gemini

    ollama = OllamaClient()
    if ollama.is_available():
        logger.info("Ollama prêt — modèle %s", ollama.model)
        return ollama

    logger.warning(
        "Bascule vers MockOllamaClient (aucun moteur IA configuré ou disponible)."
    )
    return MockOllamaClient()


def describe_analysis_engine(client: AnalysisClient) -> str:
    """Libellé moteur + modèle pour l'interface (statut de traitement)."""
    from app.services.gemini_client import GeminiClient
    from app.services.mock_ollama_client import MockOllamaClient
    from app.services.ollama_client import OllamaClient
    from app.services.openrouter_client import OpenRouterClient

    if isinstance(client, OpenRouterClient):
        return f"OpenRouter ({client.model_name})"
    if isinstance(client, GeminiClient):
        return f"Gemini ({client.model_name})"
    if isinstance(client, OllamaClient):
        return f"Ollama ({client.model})"
    if isinstance(client, MockOllamaClient):
        return "mode démo"
    return "IA"
