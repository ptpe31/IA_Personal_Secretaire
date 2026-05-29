"""Client Ollama vision pour l'analyse documentaire locale."""

from __future__ import annotations

import base64
import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS
from app.db.connection import get_setting
from app.models.analysis import DocumentAnalysis
from app.services.mock_ollama_client import MockOllamaClient
from app.utils.file_preview import load_image_bytes_for_vision

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un assistant secrétaire pour un entrepreneur français.
Analyse ce document (courrier, facture, capture d'écran d'e-mail, photo).
Extrais les informations et réponds UNIQUEMENT en JSON valide avec les clés :
title, date_emission (ISO), date_event (ISO ou null), deadline (ISO ou null),
category ("pro" ou "perso"), tags (array strings), confidence (0-1), raw_summary.
Dates : format YYYY-MM-DD. Si date absente, date_emission = aujourd'hui.
Pour deadline, extrais la date limite OFFICIELLE telle qu'indiquée sur le document.
Ne modifie pas la date pour ajouter une marge : le système de relance gère les alertes.
raw_summary : résumé textuel du contenu du document pour recherche ultérieure.
Réponds en français pour title et raw_summary."""


class AnalysisClient(ABC):
    """Interface commune Ollama / Mock."""

    is_mock: bool = False

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def analyze_document(self, file_path: Path) -> DocumentAnalysis: ...

    @property
    def warning_message(self) -> str | None:
        return None


class OllamaClient(AnalysisClient):
    """Interagit avec l'API locale Ollama (llama3.2-vision)."""

    is_mock = False

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = OLLAMA_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = (base_url or get_setting("ollama_base_url") or OLLAMA_BASE_URL).rstrip(
            "/"
        )
        self.model = model or get_setting("ollama_model") or OLLAMA_MODEL
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            models = response.json().get("models", [])
            installed = {m.get("name", "").split(":")[0] for m in models}
            target = self.model.split(":")[0]
            return target in installed
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            logger.debug("Ollama indisponible : %s", exc)
            return False

    def analyze_document(self, file_path: Path) -> DocumentAnalysis:
        image_b64 = base64.b64encode(load_image_bytes_for_vision(file_path)).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Analyse ce document et renvoie le JSON demandé.",
                    "images": [image_b64],
                },
            ],
            "stream": False,
            "format": "json",
        }

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            data = self._parse_json_content(content)
            data = self._sanitize_llm_payload(data)
            return DocumentAnalysis.model_validate(data)
        except Exception as exc:
            logger.error("Échec analyse Ollama pour %s : %s", file_path.name, exc)
            raise

    @staticmethod
    def _parse_json_content(content: str) -> dict:
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                raise ValueError("Réponse Ollama sans JSON valide") from None
            return json.loads(match.group())

    @staticmethod
    def _sanitize_llm_payload(data: dict) -> dict:
        """Corrige les artefacts JSON fréquents des modèles locaux."""
        cleaned = dict(data)
        for key in ("date_event", "deadline", "date_emission"):
            value = cleaned.get(key)
            if isinstance(value, str) and value.strip().lower() in (
                "null",
                "none",
                "",
                "n/a",
            ):
                cleaned[key] = None
        if cleaned.get("raw_summary") is None:
            cleaned["raw_summary"] = ""
        return cleaned


def get_analysis_client() -> AnalysisClient:
    """
    Retourne OllamaClient si le modèle est prêt, sinon MockOllamaClient.
    """
    client = OllamaClient()
    if client.is_available():
        logger.info("Ollama prêt — modèle %s", client.model)
        return client

    logger.warning("Bascule vers MockOllamaClient (Ollama injoignable ou modèle absent).")
    return MockOllamaClient()
