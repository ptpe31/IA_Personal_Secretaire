"""Récurrence virtuelle — mensuelle / trimestrielle / annuelle."""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

FREQUENCE_VALUES = frozenset({"mensuelle", "trimestrielle", "annuelle"})

FREQUENCE_LABELS: dict[str, str | None] = {
    "Aucune": None,
    "Mensuelle": "mensuelle",
    "Trimestrielle": "trimestrielle",
    "Annuelle": "annuelle",
}

FREQUENCE_SELECT_OPTIONS = list(FREQUENCE_LABELS.keys())

FREQUENCE_DISPLAY: dict[str, str] = {
    "mensuelle": "Mensuelle",
    "trimestrielle": "Trimestrielle",
    "annuelle": "Annuelle",
}


def frequence_from_label(label: str) -> str | None:
    """Convertit le libellé UI en valeur SQLite."""
    return FREQUENCE_LABELS.get(label)


def label_from_frequence(value: str | None) -> str:
    """Convertit la valeur SQLite en libellé UI."""
    if not value:
        return "Aucune"
    for label, stored in FREQUENCE_LABELS.items():
        if stored == value:
            return label
    return "Aucune"


def calculer_prochaine_echeance(date_actuelle: date, frequence: str) -> date:
    """Calcule la prochaine échéance selon la fréquence (récurrence virtuelle)."""
    if frequence == "mensuelle":
        return date_actuelle + relativedelta(months=1)
    if frequence == "trimestrielle":
        return date_actuelle + relativedelta(months=3)
    if frequence == "annuelle":
        return date_actuelle + relativedelta(years=1)
    raise ValueError(f"Fréquence inconnue : {frequence}")
