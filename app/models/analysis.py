"""Modèles Pydantic pour l'analyse documentaire IA."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.tags import normalize_tags


def coerce_optional_date(value: object) -> date | None:
    """Normalise les valeurs nulles renvoyées par l'IA (null, \"null\", vide…)."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in ("", "null", "none", "n/a", "na", "-", "—"):
            return None
        return date.fromisoformat(cleaned[:10])
    return None


def coerce_required_date(value: object) -> date:
    """Date obligatoire avec repli sur aujourd'hui si l'IA renvoie une valeur vide."""
    optional = coerce_optional_date(value)
    if optional is not None:
        return optional
    return date.today()


class TaskAnalysisItem(BaseModel):
    """Une tâche actionnable extraite d'un document."""

    title: str = Field(..., min_length=1)
    date_emission: date
    date_event: date | None = None
    deadline: date | None = None
    category: Literal["pro", "perso"] = "pro"
    tags: list[str] = Field(default_factory=list, max_length=5)
    justification_proof: str = "Aucune"
    suggestion: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    frequence: Literal["mensuelle", "trimestrielle", "annuelle"] | None = None
    source_url: str | None = None

    @field_validator("date_emission", mode="before")
    @classmethod
    def normalize_date_emission(cls, value: object) -> date:
        return coerce_required_date(value)

    @field_validator("date_event", "deadline", mode="before")
    @classmethod
    def normalize_optional_dates(cls, value: object) -> date | None:
        return coerce_optional_date(value)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags_field(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return normalize_tags(value)
        return normalize_tags(list(value))

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: object) -> str:
        if value is None:
            return "pro"
        normalized = str(value).strip().lower()
        if normalized in ("perso", "personal", "privé", "prive"):
            return "perso"
        return "pro"

    @field_validator("justification_proof", mode="before")
    @classmethod
    def normalize_proof(cls, value: object) -> str:
        if value is None:
            return "Aucune"
        text = str(value).strip()
        return text or "Aucune"

    @field_validator("suggestion", mode="before")
    @classmethod
    def normalize_suggestion(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if text.lower() in ("", "null", "none", "n/a", "na", "-", "—"):
            return None
        return text

    @field_validator("frequence", mode="before")
    @classmethod
    def normalize_frequence(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in ("", "null", "none", "n/a", "na", "-", "—", "aucune"):
            return None
        mapping = {
            "mensuel": "mensuelle",
            "mensuelle": "mensuelle",
            "monthly": "mensuelle",
            "mois": "mensuelle",
            "trimestriel": "trimestrielle",
            "trimestrielle": "trimestrielle",
            "quarterly": "trimestrielle",
            "trimestre": "trimestrielle",
            "annuel": "annuelle",
            "annuelle": "annuelle",
            "yearly": "annuelle",
            "an": "annuelle",
        }
        return mapping.get(text)

    @field_validator("source_url", mode="before")
    @classmethod
    def normalize_source_url(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if text.lower() in ("", "null", "none", "n/a", "na", "-", "—"):
            return None
        if not text.startswith(("http://", "https://")):
            text = f"https://{text.lstrip('/')}"
        return text


class DocumentAnalysisResult(BaseModel):
    """Résultat multi-tâches d'une analyse documentaire."""

    tasks: list[TaskAnalysisItem] = Field(..., min_length=1)
    document_summary: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @property
    def primary_task(self) -> TaskAnalysisItem:
        return self.tasks[0]


# Alias rétrocompatibilité (1 tâche = 1 item)
DocumentAnalysis = TaskAnalysisItem


def normalize_analysis_payload(data: dict) -> dict:
    """Convertit l'ancien format mono-tâche en format multi-tâches."""
    if "tasks" in data:
        cleaned = dict(data)
        if cleaned.get("document_summary") is None:
            cleaned["document_summary"] = cleaned.get("raw_summary") or ""
        return cleaned

    task_keys = (
        "title",
        "date_emission",
        "date_event",
        "deadline",
        "category",
        "tags",
        "justification_proof",
        "suggestion",
        "confidence",
        "frequence",
        "source_url",
    )
    task = {key: data[key] for key in task_keys if key in data}
    if "justification_proof" not in task:
        task["justification_proof"] = "Aucune"

    return {
        "tasks": [task],
        "document_summary": data.get("raw_summary") or data.get("document_summary") or "",
        "confidence": data.get("confidence", task.get("confidence", 0.5)),
    }
