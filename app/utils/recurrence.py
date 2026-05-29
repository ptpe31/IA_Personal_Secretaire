"""Calcul des occurrences récurrentes de tâches."""

from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

RECURRENCE_PATTERNS = frozenset({"daily", "weekly", "monthly"})

RECURRENCE_LABELS: dict[str, str | None] = {
    "Aucune": None,
    "Quotidien": "daily",
    "Hebdomadaire": "weekly",
    "Mensuel": "monthly",
}

RECURRENCE_SELECT_OPTIONS = list(RECURRENCE_LABELS.keys())

RECURRENCE_DISPLAY: dict[str, str] = {
    "daily": "Quotidien",
    "weekly": "Hebdomadaire",
    "monthly": "Mensuel",
}


def pattern_from_label(label: str) -> str | None:
    """Convertit le libellé UI en valeur SQLite."""
    return RECURRENCE_LABELS.get(label)


def compute_next_occurrence(from_date: date, pattern: str) -> date:
    """Calcule la prochaine échéance à partir d'une date de référence."""
    if pattern == "daily":
        return from_date + timedelta(days=1)
    if pattern == "weekly":
        return from_date + timedelta(days=7)
    if pattern == "monthly":
        return from_date + relativedelta(months=1)
    raise ValueError(f"Récurrence inconnue : {pattern}")
