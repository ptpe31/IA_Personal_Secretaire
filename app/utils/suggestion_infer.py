"""Inférence de suggestions actionnables depuis le texte d'un document."""

from __future__ import annotations

import re


def infer_rehearsal_suggestion(blob: str) -> str | None:
    match = re.search(r"(\d{1,2}h(?:\s*à\s*\d{1,2}h)?)", blob, re.IGNORECASE)
    if match:
        return f"Horaires de l'atelier : {match.group(1)}"
    return None


def infer_spectacle_suggestion(blob: str) -> str | None:
    phone = re.search(r"0[1-9](?:[\s.\-]?\d{2}){4}", blob)
    if phone and re.search(r"inscription|inscri|mail|telephone|téléphone", blob, re.I):
        return f"Faire l'inscription par mail ou au {phone.group(0)}"
    if phone:
        return f"Contacter le {phone.group(0)} pour toute action requise"
    if re.search(r"inscription", blob, re.I):
        return "Faire l'inscription par mail"
    return None
