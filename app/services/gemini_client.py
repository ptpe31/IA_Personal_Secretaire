"""Client Google Gemini pour l'analyse documentaire multimodale."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import google.generativeai as genai
from pydantic import BaseModel

from app.config import GEMINI_MODEL, get_gemini_api_key
from app.db.connection import get_setting
from app.models.analysis import DocumentAnalysisResult
from app.services.analysis_client import AnalysisClient
from app.services.analysis_pipeline import finalize_document_analysis, parse_json_content
from app.services.analysis_prompt import build_system_prompt
from app.utils.file_preview import load_image_bytes_for_vision

logger = logging.getLogger(__name__)

USER_PROMPT = (
    "Analyse ce document. Découpe en autant de tâches que nécessaire "
    "(une par date ou événement distinct) et renvoie le JSON demandé."
)

# Mots-clés JSON Schema non supportés par protos.Schema de google-generativeai.
_GEMINI_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "pattern",
        "$schema",
        "$id",
        "title",
        "default",
        "additionalProperties",
        "const",
        "examples",
    }
)


def gemini_response_schema(model: type[BaseModel]) -> dict[str, Any]:
    """
    Convertit un modèle Pydantic en schéma compatible Gemini.

    Le SDK refuse les champs Pydantic comme minItems (Field(min_length=1)).
    """
    raw = model.model_json_schema()
    defs: dict[str, Any] = raw.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                if ref.startswith("#/$defs/"):
                    return resolve(defs[ref.rsplit("/", 1)[-1]])
            cleaned: dict[str, Any] = {}
            for key, value in node.items():
                if key in _GEMINI_UNSUPPORTED_SCHEMA_KEYS:
                    continue
                if key == "anyOf":
                    # Optionnel Pydantic (T | null) → nullable Gemini
                    variants = [item for item in value if item != {"type": "null"}]
                    if len(variants) == 1:
                        resolved = resolve(variants[0])
                        if isinstance(resolved, dict):
                            resolved = dict(resolved)
                            resolved["nullable"] = True
                            return resolved
                cleaned[key] = resolve(value)
            return cleaned
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(raw)


class GeminiClient(AnalysisClient):
    """Interagit avec l'API Google Gemini (vision + JSON structuré)."""

    is_mock = False

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.api_key = (api_key or get_gemini_api_key() or "").strip()
        self.model_name = (
            model_name or get_setting("gemini_model") or GEMINI_MODEL
        ).strip()

    def is_available(self) -> bool:
        return bool(self.api_key)

    def analyze_document(self, file_path: Path) -> DocumentAnalysisResult:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY non configurée.")

        genai.configure(api_key=self.api_key)
        image_bytes = load_image_bytes_for_vision(file_path)
        mime_type = _vision_mime_type(file_path)

        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=gemini_response_schema(DocumentAnalysisResult),
        )
        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=build_system_prompt(),
            generation_config=generation_config,
        )

        try:
            response = model.generate_content(
                [
                    USER_PROMPT,
                    {"mime_type": mime_type, "data": image_bytes},
                ]
            )
            content = response.text
            if not content:
                raise ValueError("Réponse Gemini vide")
            logger.debug("Réponse Gemini brute pour %s :\n%s", file_path.name, content)
            data = parse_json_content(content)
            return finalize_document_analysis(
                data,
                file_path=file_path,
                stage_prefix="GEMINI",
            )
        except Exception as exc:
            logger.error("Échec analyse Gemini pour %s : %s", file_path.name, exc)
            raise


def _vision_mime_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"
