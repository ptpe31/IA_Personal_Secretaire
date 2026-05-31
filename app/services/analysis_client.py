"""Interface et factory pour les clients d'analyse documentaire."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import IA_PROVIDER_GEMINI, IA_PROVIDER_OPENROUTER, get_active_ia_provider
from app.models.analysis import DocumentAnalysisResult
from app.models.drive import DriveMenuAnalysisResult, DriveMenuInput

logger = logging.getLogger(__name__)


class AnalysisClient(ABC):
    """Interface commune Gemini / OpenRouter / Ollama / Mock."""

    is_mock: bool = False

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def analyze_document(self, file_path: Path) -> DocumentAnalysisResult: ...

    def analyze_drive_menu(self, payload: DriveMenuInput) -> DriveMenuAnalysisResult:
        raise NotImplementedError(
            f"{type(self).__name__} ne prend pas en charge analyze_drive_menu."
        )

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


def get_drive_analysis_client() -> AnalysisClient:
    """
    Client IA Menu & Drive — Gemini / OpenRouter uniquement (pas Ollama, pas Mock).
    Respecte active_ia_provider avec repli croisé cloud si le provider choisi est indisponible.
    """
    from app.services.gemini_client import GeminiClient
    from app.services.openrouter_client import OpenRouterClient

    provider = get_active_ia_provider()
    openrouter = OpenRouterClient()
    gemini = GeminiClient()

    if provider == IA_PROVIDER_OPENROUTER:
        if openrouter.is_available():
            logger.info("[DRIVE-IA] OpenRouter — modèle %s", openrouter.model_name)
            return openrouter
        if gemini.is_available():
            logger.warning("[DRIVE-IA] OpenRouter indisponible — repli Gemini.")
            return gemini
    else:
        if gemini.is_available():
            logger.info("[DRIVE-IA] Gemini — modèle %s", gemini.model_name)
            return gemini
        if openrouter.is_available():
            logger.warning("[DRIVE-IA] Gemini indisponible — repli OpenRouter.")
            return openrouter

    raise RuntimeError(
        "Aucun moteur IA cloud disponible pour Menu & Drive. "
        "Configurez GEMINI_API_KEY ou OPENROUTER_API_KEY dans Paramètres / .env."
    )


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
