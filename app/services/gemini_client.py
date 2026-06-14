"""Client Google Gemini — SDK google.genai (vision + JSON structuré)."""

from __future__ import annotations

import logging
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.config import get_gemini_api_key, get_gemini_model
from app.models.analysis import DocumentAnalysisResult
from app.models.drive import DriveMenuAnalysisResult, DriveMenuInput, resolve_allowed_meal_slots, resolve_allowed_regime_slots
from app.services.analysis_client import AnalysisClient
from app.services.analysis_pipeline import finalize_document_analysis, parse_json_content
from app.services.drive_analysis_pipeline import finalize_drive_analysis
from app.services.drive_prompt import build_drive_system_prompt, build_drive_user_prompt
from app.services.analysis_prompt import build_gemini_system_prompt
from app.utils.file_preview import load_image_bytes_for_vision

logger = logging.getLogger(__name__)

USER_PROMPT = (
    "Analyse ce document. Extrais chaque événement ou échéance distinct "
    "dans le tableau tasks. JSON strict uniquement."
)

_LOG_SEPARATOR = "=" * 72
_LOG_SUB_SEPARATOR = "-" * 72


def _mask_api_key(key: str) -> str:
    if not key:
        return "(absente)"
    if key.strip().lower() in ("votre_cle_api_google", "your_api_key", "changeme"):
        return "(placeholder .env — clé non configurée)"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}…{key[-4:]} ({len(key)} car.)"


def _log_gemini_request(
    *,
    filename: str,
    model_name: str,
    api_key: str,
    mime_type: str,
    image_size: int,
    system_prompt: str,
) -> None:
    body = "\n".join(
        [
            _LOG_SEPARATOR,
            f"[GEMINI — requête] Document : {filename}",
            _LOG_SUB_SEPARATOR,
            f"  modèle            : {model_name}",
            f"  clé API           : {_mask_api_key(api_key)}",
            f"  mime image        : {mime_type}",
            f"  taille image      : {image_size} octets",
            f"  temperature       : 0.0",
            f"  response_mime     : application/json",
            f"  response_schema   : DocumentAnalysisResult (Pydantic natif)",
            _LOG_SUB_SEPARATOR,
            "  --- system_instruction ---",
            system_prompt,
            _LOG_SUB_SEPARATOR,
            "  --- user_prompt ---",
            USER_PROMPT,
            _LOG_SEPARATOR,
        ]
    )
    logger.info("\n%s", body)


def _log_gemini_response(*, filename: str, content: str) -> None:
    logger.info(
        "\n%s\n[GEMINI — réponse OK] %s | %s car.\n%s\n%s",
        _LOG_SEPARATOR,
        filename,
        len(content),
        content,
        _LOG_SEPARATOR,
    )


def _log_gemini_failure(
    *,
    filename: str,
    exc: Exception,
    system_prompt: str,
) -> None:
    body = "\n".join(
        [
            _LOG_SEPARATOR,
            f"[GEMINI — ÉCHEC] Document : {filename}",
            _LOG_SUB_SEPARATOR,
            f"  type exception    : {type(exc).__name__}",
            f"  message           : {exc}",
            _LOG_SUB_SEPARATOR,
            "  --- system_instruction ---",
            system_prompt,
            _LOG_SEPARATOR,
        ]
    )
    logger.error("\n%s", body, exc_info=True)


class GeminiClient(AnalysisClient):
    """Analyse documentaire via google.genai — modèle gemini-2.5-flash."""

    is_mock = False

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.api_key = (api_key or get_gemini_api_key() or "").strip()
        self.model_name = (model_name or get_gemini_model()).strip()

    def is_available(self) -> bool:
        return bool(self.api_key)

    def analyze_document(self, file_path: Path) -> DocumentAnalysisResult:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY non configurée.")

        client = genai.Client(api_key=self.api_key)
        image_bytes = load_image_bytes_for_vision(file_path)
        mime_type = _vision_mime_type(file_path)
        system_prompt = build_gemini_system_prompt()

        logger.info(
            "Gemini — début analyse « %s » (modèle=%s, image=%s, %s octets)",
            file_path.name,
            self.model_name,
            mime_type,
            len(image_bytes),
        )

        _log_gemini_request(
            filename=file_path.name,
            model_name=self.model_name,
            api_key=self.api_key,
            mime_type=mime_type,
            image_size=len(image_bytes),
            system_prompt=system_prompt,
        )

        config = types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=DocumentAnalysisResult,
            system_instruction=system_prompt,
        )

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=USER_PROMPT),
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        ],
                    )
                ],
                config=config,
            )
            content = response.text or ""
            if not content:
                raise ValueError("Réponse Gemini vide")
            _log_gemini_response(filename=file_path.name, content=content)
            data = parse_json_content(content)
            return finalize_document_analysis(
                data,
                file_path=file_path,
                stage_prefix="GEMINI",
            )
        except ValidationError as exc:
            _log_gemini_failure(
                filename=file_path.name,
                exc=exc,
                system_prompt=system_prompt,
            )
            raise
        except Exception as exc:
            _log_gemini_failure(
                filename=file_path.name,
                exc=exc,
                system_prompt=system_prompt,
            )
            raise


    def analyze_drive_menu(self, payload: DriveMenuInput) -> DriveMenuAnalysisResult:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY non configurée.")

        client = genai.Client(api_key=self.api_key)
        system_prompt = build_drive_system_prompt(payload)
        user_prompt = build_drive_user_prompt(payload)

        logger.info(
            "[DRIVE-IA] Gemini — menu (%s plats manuels, %s créneaux consignes enfants, "
            "%s plats régime manuels, %s créneaux consignes régime, modèle=%s)",
            len(payload.plats),
            len(payload.enfants_creneaux_cibles),
            len(payload.regime_plats),
            len(payload.regime_creneaux_cibles),
            self.model_name,
        )
        logger.debug("[DRIVE-IA] user prompt (500 car.): %s", user_prompt[:500])

        config = types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=DriveMenuAnalysisResult,
            system_instruction=system_prompt,
        )

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=[types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])],
                config=config,
            )
            content = response.text or ""
            if not content:
                raise ValueError("Réponse Gemini vide (Menu & Drive)")
            logger.info("[DRIVE-IA] Gemini — réponse OK (%s car.)", len(content))
            data = parse_json_content(content)
            return finalize_drive_analysis(
                data,
                allowed_slots=resolve_allowed_meal_slots(payload),
                allowed_regime_slots=resolve_allowed_regime_slots(payload),
                premier_jour_semaine=payload.premier_jour_semaine,
            )
        except ValidationError:
            logger.exception("[DRIVE-IA] Gemini — validation Pydantic échouée")
            raise
        except Exception:
            logger.exception("[DRIVE-IA] Gemini — échec analyse menu")
            raise


def _vision_mime_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"
