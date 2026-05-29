"""Modèles Pydantic pour l'analyse documentaire IA."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


class DocumentAnalysis(BaseModel):
    """JSON structuré attendu de l'IA (spec §5.2)."""

    title: str = Field(..., min_length=1)
    date_emission: date
    date_event: date | None = None
    deadline: date | None = None
    category: Literal["pro", "perso"] = "pro"
    tags: list[str] = Field(default_factory=list, max_length=5)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    raw_summary: str = ""

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
    def normalize_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        tags: list[str] = []
        for tag in value:
            cleaned = str(tag).strip().lstrip("#")
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
        return tags[:5]

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: object) -> str:
        if value is None:
            return "pro"
        normalized = str(value).strip().lower()
        if normalized in ("perso", "personal", "privé", "prive"):
            return "perso"
        return "pro"
