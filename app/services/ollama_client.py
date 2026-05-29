"""Client Ollama vision pour l'analyse documentaire locale (fallback)."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS
from app.db.connection import get_setting
from app.models.analysis import DocumentAnalysisResult
from app.services.analysis_client import AnalysisClient
from app.services.analysis_pipeline import finalize_document_analysis, parse_json_content
from app.services.analysis_prompt import build_system_prompt
from app.utils.file_preview import load_image_bytes_for_vision

logger = logging.getLogger(__name__)


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

    def analyze_document(self, file_path: Path) -> DocumentAnalysisResult:
        image_b64 = base64.b64encode(load_image_bytes_for_vision(file_path)).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": build_system_prompt()},
                {
                    "role": "user",
                    "content": (
                        "Analyse ce document. Découpe en autant de tâches que nécessaire "
                        "(une par date ou événement distinct) et renvoie le JSON demandé."
                    ),
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
            logger.debug("Réponse Ollama brute pour %s :\n%s", file_path.name, content)
            data = parse_json_content(content)
            return finalize_document_analysis(
                data,
                file_path=file_path,
                stage_prefix="OLLAMA",
            )
        except Exception as exc:
            logger.error("Échec analyse Ollama pour %s : %s", file_path.name, exc)
            raise
