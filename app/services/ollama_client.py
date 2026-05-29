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
from app.models.analysis import DocumentAnalysisResult, normalize_analysis_payload
from app.services.mock_ollama_client import MockOllamaClient
from app.services.task_expansion import expand_analysis_tasks
from app.utils.analysis_logging import log_analysis_result
from app.utils.dates import format_today_anchor
from app.utils.file_preview import load_image_bytes_for_vision

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Tu es un assistant secrétaire d'élite pour un entrepreneur français.
{today_anchor}

Analyse le document fourni (courrier, facture, capture d'écran d'e-mail, photo).
Un même document peut contenir PLUSIEURS événements ou dates actionnables : tu dois impérativement créer une tâche distincte pour chaque date importante (répétitions, rendez-vous, échéances, spectacles…).

Réponds UNIQUEMENT en JSON valide avec cette structure exacte :
{{
  "tasks": [
    {{
      "title": "Titre contextuel court et explicite",
      "date_emission": "YYYY-MM-DD",
      "date_event": "YYYY-MM-DD ou null",
      "deadline": "YYYY-MM-DD ou null",
      "category": "pro ou perso",
      "tags": ["motcle1", "motcle2"],
      "justification_proof": "Phrase EXACTE extraite du document",
      "suggestion": "Action immédiate ou rappel logistique court"
    }}
  ],
  "document_summary": "Résumé global",
  "confidence": 0.0
}}

### EXEMPLE DE COMPORTEMENT ATTENDU (FEW-SHOT) ###
Si le document est un e-mail reçu le 26 mai 2026 concernant des cours de Hip-Hop avec des répétitions les 4, 11, 18 et 25 juin de 18h à 19h et un spectacle le samedi 27 juin 2026 (inscription par mail ou au 05.62.11.62.66), tu dois générer EXACTEMENT 5 tâches distinctes comme ceci :
- Tâche 1 : "Répétition Hip-Hop (1/4)" -> deadline & date_event: 2026-06-04 | suggestion: "Horaires de l'atelier : 18h à 19h"
- Tâche 2 : "Répétition Hip-Hop (2/4)" -> deadline & date_event: 2026-06-11 | suggestion: "Horaires de l'atelier : 18h à 19h"
- Tâche 3 : "Répétition Hip-Hop (3/4)" -> deadline & date_event: 2026-06-18 | suggestion: "Horaires de l'atelier : 18h à 19h"
- Tâche 4 : "Répétition Hip-Hop (4/4)" -> deadline & date_event: 2026-06-25 | suggestion: "Horaires de l'atelier : 18h à 19h"
- Tâche 5 : "Spectacle Hip-Hop de fin d'année" -> deadline & date_event: 2026-06-27 | suggestion: "Faire l'inscription par mail ou au 05.62.11.62.66"

Règles strictes :
1. Découpage temporel : Si une liste de dates est présente (ex: "les 4, 11, 18"), génère une tâche par date. Ne les regroupe JAMAIS.
2. Ancrage {current_year} : Utilise l'année courante ({current_year}) pour interpréter les mois cités (ex: "25 juin" -> {current_year}-06-25).
3. Justification : 'justification_proof' doit contenir l'extrait brut (ex: "les répétitions auront lieu le 4, 11, 18").
4. Tags : Mots-clés uniques, minuscules, sans accents ni caractères corrompus (ex: "repetition", "danse"). Max 5.
5. Suggestion : "suggestion" est une recommandation d'action immédiate ou un rappel logistique ultra-court extrait du contexte (numéro de téléphone, action à faire comme "faire inscription", horaires précis comme "Atelier de 18h à 19h"). Si le document ne s'y prête pas, propose une action logique par défaut liée à la tâche."""


def build_system_prompt() -> str:
    from datetime import date

    today = date.today()
    return SYSTEM_PROMPT_TEMPLATE.format(
        today_anchor=format_today_anchor(today),
        current_year=today.year,
    )


class AnalysisClient(ABC):
    """Interface commune Ollama / Mock."""

    is_mock: bool = False

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def analyze_document(self, file_path: Path) -> DocumentAnalysisResult: ...

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
            data = self._parse_json_content(content)
            data = self._sanitize_llm_payload(data)
            data = normalize_analysis_payload(data)
            result = DocumentAnalysisResult.model_validate(data)
            log_analysis_result(
                logger,
                stage="OLLAMA brut (avant expansion)",
                filename=file_path.name,
                result=result,
            )
            expanded = expand_analysis_tasks(result)
            if len(expanded.tasks) != len(result.tasks):
                log_analysis_result(
                    logger,
                    stage="POST-EXPANSION dates",
                    filename=file_path.name,
                    result=expanded,
                    extra=f"{len(result.tasks)} → {len(expanded.tasks)} tâche(s)",
                )
            else:
                logger.info(
                    "Analyse %s — expansion non appliquée (%s tâche(s))",
                    file_path.name,
                    len(expanded.tasks),
                )
            return expanded
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

        if "tasks" in cleaned and isinstance(cleaned["tasks"], list):
            for task in cleaned["tasks"]:
                if not isinstance(task, dict):
                    continue
                for key in ("date_event", "deadline", "date_emission", "suggestion"):
                    value = task.get(key)
                    if isinstance(value, str) and value.strip().lower() in (
                        "null",
                        "none",
                        "",
                        "n/a",
                    ):
                        task[key] = None
        else:
            for key in ("date_event", "deadline", "date_emission"):
                value = cleaned.get(key)
                if isinstance(value, str) and value.strip().lower() in (
                    "null",
                    "none",
                    "",
                    "n/a",
                ):
                    cleaned[key] = None

        if cleaned.get("document_summary") is None and cleaned.get("raw_summary") is None:
            cleaned["document_summary"] = ""
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
