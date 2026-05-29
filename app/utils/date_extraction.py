"""Extraction de dates françaises depuis le texte d'un document."""

from __future__ import annotations

import re
from datetime import date

_MONTHS: dict[str, int] = {
    "janvier": 1,
    "fevrier": 2,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    "décembre": 12,
}

_WEEKDAY_PREFIX = r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+"
_MONTH_PATTERN = (
    r"(janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|"
    r"septembre|octobre|novembre|d[eé]cembre)"
)


def _month_number(name: str) -> int:
    key = name.lower().replace("û", "u").replace("é", "e").replace("è", "e")
    if key in _MONTHS:
        return _MONTHS[key]
    for month_name, number in _MONTHS.items():
        if key.startswith(month_name[:3]):
            return number
    raise ValueError(f"Mois inconnu : {name}")


def _add_event(
    events: list[tuple[date, str]],
    seen: set[date],
    event_date: date,
    snippet: str,
) -> None:
    if event_date in seen:
        return
    seen.add(event_date)
    events.append((event_date, snippet.strip()))


def extract_french_event_dates(text: str, *, default_year: int | None = None) -> list[tuple[date, str]]:
    """Repère les dates d'événements dans un texte français."""
    if not text.strip():
        return []

    year = default_year or date.today().year
    events: list[tuple[date, str]] = []
    seen: set[date] = set()

    list_pattern = re.compile(
        rf"([\d\s,et]+)\s+{_MONTH_PATTERN}(?:\s+(\d{{4}}))?",
        re.IGNORECASE,
    )
    for match in list_pattern.finditer(text):
        days_part = match.group(1)
        if "," not in days_part and " et " not in days_part.lower():
            continue
        month = _month_number(match.group(2))
        event_year = int(match.group(3)) if match.group(3) else year
        snippet = match.group(0)
        for day_str in re.findall(r"\d+", days_part):
            _add_event(events, seen, date(event_year, month, int(day_str)), snippet)

    single_pattern = re.compile(
        rf"(?:{_WEEKDAY_PREFIX})?(\d{{1,2}})\s+{_MONTH_PATTERN}(?:\s+(\d{{4}}))?",
        re.IGNORECASE,
    )
    for match in single_pattern.finditer(text):
        day = int(match.group(1))
        month = _month_number(match.group(2))
        event_year = int(match.group(3)) if match.group(3) else year
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + 40)
        snippet = text[start:end]
        _add_event(events, seen, date(event_year, month, day), snippet)

    events.sort(key=lambda item: item[0])
    return events
