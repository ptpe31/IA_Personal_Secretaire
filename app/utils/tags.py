"""Normalisation des tags extraits par l'IA."""

from __future__ import annotations

import re
import unicodedata

_STOP_WORDS = frozenset(
    {"de", "du", "des", "le", "la", "les", "un", "une", "et", "a", "au", "aux", "en"}
)


def normalize_tag(value: str) -> str:
    """Nettoie un mot-clé : minuscules, ASCII, sans caractères corrompus."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value.strip().lstrip("#"))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "", ascii_text)
    return ascii_text[:20]


def normalize_tags(values: list[str] | str | None, *, max_tags: int = 5) -> list[str]:
    """Normalise une liste ou une phrase de tags en mots-clés uniques."""
    if values is None:
        return []
    if isinstance(values, str):
        parts = re.split(r"[\s,;]+", values)
    else:
        parts: list[str] = []
        for item in values:
            parts.extend(re.split(r"[\s,;]+", str(item)))

    result: list[str] = []
    for part in parts:
        tag = normalize_tag(part)
        if tag and tag not in _STOP_WORDS and tag not in result:
            result.append(tag)
        if len(result) >= max_tags:
            break
    return result
