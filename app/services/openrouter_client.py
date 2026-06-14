"""Client OpenRouter (Qwen VL) pour l'analyse documentaire — mode Éco."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from app.config import (
    OPENROUTER_API_URL,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_TIMEOUT_SECONDS,
    get_openrouter_api_key,
    get_openrouter_model,
)
from app.models.analysis import DocumentAnalysisResult
from app.models.drive import DriveMenuAnalysisResult, DriveMenuInput, resolve_allowed_meal_slots, resolve_allowed_regime_slots
from app.services.analysis_client import AnalysisClient
from app.services.analysis_pipeline import finalize_document_analysis, parse_json_content
from app.services.drive_analysis_pipeline import finalize_drive_analysis
from app.services.drive_prompt import build_drive_system_prompt, build_drive_user_prompt
from app.services.analysis_prompt import build_system_prompt
from app.utils.file_preview import load_image_bytes_for_vision

logger = logging.getLogger(__name__)

USER_PROMPT = (
    "Analyse ce document et extrais chaque événement ou échéance distinct "
    "dans le tableau tasks. JSON strict uniquement."
)


def _vision_mime_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


class OpenRouterClient(AnalysisClient):
    """Analyse vision via OpenRouter (API compatible OpenAI Chat Completions)."""

    is_mock = False

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout: int = OPENROUTER_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = (api_key or get_openrouter_api_key() or "").strip()
        self.model_name = (model_name or get_openrouter_model()).strip()
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(self.api_key)

    def analyze_document(self, file_path: Path) -> DocumentAnalysisResult:
        if not self.api_key:
            raise RuntimeError("Clé OpenRouter non configurée.")

        image_bytes = load_image_bytes_for_vision(file_path)
        mime_type = _vision_mime_type(file_path)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        system_prompt = build_system_prompt()

        logger.info(
            "OpenRouter — début analyse « %s » (modèle=%s, image=%s, %s octets)",
            file_path.name,
            self.model_name,
            mime_type,
            len(image_bytes),
        )

        payload = {
            "model": self.model_name,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}",
                            },
                        },
                    ],
                },
            ],
            "temperature": 0.0,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": OPENROUTER_HTTP_REFERER,
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                OPENROUTER_API_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not content:
                raise ValueError("Réponse OpenRouter vide")
            logger.info(
                "OpenRouter — réponse OK pour %s (%s car.)",
                file_path.name,
                len(content),
            )
            data = parse_json_content(content)
            return finalize_document_analysis(
                data,
                file_path=file_path,
                stage_prefix="OPENROUTER",
            )
        except Exception as exc:
            logger.error(
                "OpenRouter — échec analyse « %s » : %s",
                file_path.name,
                exc,
                exc_info=True,
            )
            raise

    def analyze_drive_menu(self, payload: DriveMenuInput) -> DriveMenuAnalysisResult:
        if not self.api_key:
            raise RuntimeError("Clé OpenRouter non configurée.")

        system_prompt = build_drive_system_prompt(payload)
        user_prompt = build_drive_user_prompt(payload)

        logger.info(
            "[DRIVE-IA] OpenRouter — menu (%s plats manuels, %s créneaux consignes enfants, "
            "%s plats régime manuels, %s créneaux consignes régime, modèle=%s)",
            len(payload.plats),
            len(payload.enfants_creneaux_cibles),
            len(payload.regime_plats),
            len(payload.regime_creneaux_cibles),
            self.model_name,
        )
        logger.debug("[DRIVE-IA] user prompt (500 car.): %s", user_prompt[:500])

        payload_body = {
            "model": self.model_name,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": OPENROUTER_HTTP_REFERER,
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                OPENROUTER_API_URL,
                json=payload_body,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not content:
                raise ValueError("Réponse OpenRouter vide (Menu & Drive)")
            logger.info("[DRIVE-IA] OpenRouter — réponse OK (%s car.)", len(content))
            data = parse_json_content(content)
            return finalize_drive_analysis(
                data,
                allowed_slots=resolve_allowed_meal_slots(payload),
                allowed_regime_slots=resolve_allowed_regime_slots(payload),
                premier_jour_semaine=payload.premier_jour_semaine,
            )
        except Exception:
            logger.exception("[DRIVE-IA] OpenRouter — échec analyse menu")
            raise
