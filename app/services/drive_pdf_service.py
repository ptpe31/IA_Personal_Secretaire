"""Export PDF planning Menu & Drive — template HTML local + WeasyPrint."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app import config
from app.models.drive import (
    DriveMenuAnalysisResult,
    PLANNING_MOMENTS,
    PlanningJourType,
    PlanningRepasItem,
    escape_html,
    ordered_week_days,
    sort_planning_repas,
)
from app.utils.slugify import build_ged_filename, unique_path

logger = logging.getLogger(__name__)

_WEASYPRINT_HINT = (
    "WeasyPrint nécessite les bibliothèques système Homebrew. "
    "Installez : brew install pango gdk-pixbuf libffi "
    "et lancez via start.command (DYLD_FALLBACK_LIBRARY_PATH)."
)

_PLANNING_CSS = """
@page { size: A4 landscape; margin: 10mm; }
body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 9pt;
    color: #14532d;
    background: #f0fdf4;
    margin: 0;
    padding: 0;
}
h1 {
    font-size: 16pt;
    color: #166534;
    margin: 0 0 8px 0;
}
.meta {
    font-size: 9pt;
    color: #166534;
    margin: 0 0 12px 0;
}
table {
    width: 100%;
    border-collapse: collapse;
    background: #ffffff;
    border: 1px solid #86efac;
    table-layout: fixed;
}
thead th {
    background: #166534;
    color: #ffffff;
    font-weight: 600;
    text-align: center;
    padding: 6px 6px;
    font-size: 8pt;
    border: 1px solid #14532d;
}
thead th.col-audience,
tbody td.col-audience {
    background: #166534;
    color: #ffffff;
    font-weight: 600;
    text-align: left;
    width: 7%;
    vertical-align: middle;
}
thead th.col-moment {
    background: #15803d;
    font-size: 7pt;
    font-weight: 500;
}
tbody td {
    padding: 5px 6px;
    vertical-align: top;
    border: 1px solid #dcfce7;
    font-size: 8pt;
}
tbody tr.row-enfants td.slot-cell { background: #ffffff; }
tbody tr.row-regime td.slot-cell { background: #f0fdf4; }
tbody tr.row-batch td {
    background: #ecfdf5;
    border-top: 2px solid #86efac;
}
tbody tr.row-batch td.col-audience {
    background: #166534;
    font-size: 7pt;
}
.slot-cell .plat {
    font-weight: 600;
    color: #14532d;
    margin-bottom: 3px;
}
.slot-cell .action {
    font-size: 7pt;
    color: #166534;
}
.batch-unified {
    font-size: 7.5pt;
    line-height: 1.35;
    color: #14532d;
}
"""


def _planning_by_slot(
    items: list[PlanningRepasItem],
) -> dict[tuple[str, str], PlanningRepasItem]:
    indexed: dict[tuple[str, str], PlanningRepasItem] = {}
    for item in items:
        indexed[(item.jour, item.moment)] = item
    return indexed


def _active_planning_days(
    result: DriveMenuAnalysisResult,
    *,
    premier_jour: str,
) -> tuple[PlanningJourType, ...]:
    days_with_data: set[str] = set()
    for item in result.planning_repas + result.planning_regime:
        days_with_data.add(item.jour)
    return tuple(day for day in ordered_week_days(premier_jour) if day in days_with_data)


def _meal_cell_html(item: PlanningRepasItem | None) -> str:
    if item is None:
        return ""
    plat = escape_html(item.plat)
    action = escape_html(item.action_minute)
    return (
        f'<div class="plat">{plat}</div>'
        f'<div class="action">{action}</div>'
    )


def _unified_batch_for_day(
    jour: str,
    *,
    enfants_by_slot: dict[tuple[str, str], PlanningRepasItem],
    regime_by_slot: dict[tuple[str, str], PlanningRepasItem],
) -> str:
    """Fusionne les batch du jour en un seul bloc (dédoublonnage)."""
    chunks: list[str] = []
    seen: set[str] = set()
    for moment in PLANNING_MOMENTS:
        for slot_map in (enfants_by_slot, regime_by_slot):
            item = slot_map.get((jour, moment))
            if item is None:
                continue
            text = item.batch_cooking_dimanche.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            chunks.append(text)
    return " · ".join(chunks)


def _render_planning_grid(
    *,
    days: tuple[PlanningJourType, ...],
    enfants_by_slot: dict[tuple[str, str], PlanningRepasItem],
    regime_by_slot: dict[tuple[str, str], PlanningRepasItem],
) -> str:
    if not days:
        return '<p class="meta">Aucun créneau planifié.</p>'

    day_headers = "".join(
        f'<th colspan="2">{escape_html(day)}</th>' for day in days
    )
    moment_headers = "".join(
        '<th class="col-moment">Midi</th><th class="col-moment">Soir</th>' for _ in days
    )

    enfants_cells = "".join(
        f'<td class="slot-cell">{_meal_cell_html(enfants_by_slot.get((day, "Midi")))}</td>'
        f'<td class="slot-cell">{_meal_cell_html(enfants_by_slot.get((day, "Soir")))}</td>'
        for day in days
    )
    regime_cells = "".join(
        f'<td class="slot-cell">{_meal_cell_html(regime_by_slot.get((day, "Midi")))}</td>'
        f'<td class="slot-cell">{_meal_cell_html(regime_by_slot.get((day, "Soir")))}</td>'
        for day in days
    )
    batch_cells = "".join(
        f'<td colspan="2" class="batch-unified">{escape_html(_unified_batch_for_day(day, enfants_by_slot=enfants_by_slot, regime_by_slot=regime_by_slot))}</td>'
        for day in days
    )

    return f"""<table>
    <thead>
      <tr>
        <th class="col-audience" rowspan="2"></th>
        {day_headers}
      </tr>
      <tr>
        {moment_headers}
      </tr>
    </thead>
    <tbody>
      <tr class="row-enfants">
        <td class="col-audience">Enfants</td>
        {enfants_cells}
      </tr>
      <tr class="row-regime">
        <td class="col-audience">Convives<br/>régime</td>
        {regime_cells}
      </tr>
      <tr class="row-batch">
        <td class="col-audience">Batch<br/>dimanche</td>
        {batch_cells}
      </tr>
    </tbody>
  </table>"""


def render_planning_html(
    result: DriveMenuAnalysisResult,
    *,
    semaine_label: str,
    nb_convives_enfants: int = 4,
    nb_convives_regime: int = 4,
    premier_jour_semaine: str = "Lundi",
) -> str:
    """Assemble le HTML imprimable à partir des données structurées (sans IA)."""
    enfants_by_slot = _planning_by_slot(
        sort_planning_repas(result.planning_repas, premier_jour=premier_jour_semaine)
    )
    regime_by_slot = _planning_by_slot(
        sort_planning_repas(result.planning_regime, premier_jour=premier_jour_semaine)
    )
    days = _active_planning_days(result, premier_jour=premier_jour_semaine)
    grid_html = _render_planning_grid(
        days=days,
        enfants_by_slot=enfants_by_slot,
        regime_by_slot=regime_by_slot,
    )
    meta = (
        f"Convives enfants : {nb_convives_enfants} | "
        f"Hôte régime spécial : {nb_convives_regime}"
    )
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <title>Planning Batch Cooking — Semaine du {escape_html(semaine_label)}</title>
  <style>{_PLANNING_CSS}</style>
</head>
<body>
  <h1>Planning Batch Cooking — Semaine du {escape_html(semaine_label)}</h1>
  <p class="meta">{escape_html(meta)}</p>
  {grid_html}
</body>
</html>"""


def save_planning_pdf(
    result: DriveMenuAnalysisResult,
    *,
    semaine_label: str,
    nb_convives_enfants: int = 4,
    nb_convives_regime: int = 4,
    premier_jour_semaine: str = "Lundi",
    title: str = "Planning_Batch_Cooking",
) -> Path:
    """Génère le HTML localement puis exporte le PDF vers ~/Trankil-v2/Perso/GED/."""
    html = render_planning_html(
        result,
        semaine_label=semaine_label,
        nb_convives_enfants=nb_convives_enfants,
        nb_convives_regime=nb_convives_regime,
        premier_jour_semaine=premier_jour_semaine,
    )
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError("WeasyPrint n'est pas installé (pip install weasyprint).") from exc

    ged_dir = config.PERSO_GED_PATH
    ged_dir.mkdir(parents=True, exist_ok=True)
    filename = build_ged_filename(date.today(), title, ".pdf")
    destination = unique_path(ged_dir, filename)

    try:
        HTML(string=html).write_pdf(str(destination))
    except OSError as exc:
        logger.exception("Échec WeasyPrint — bibliothèques système manquantes")
        raise RuntimeError(_WEASYPRINT_HINT) from exc

    logger.info("[DRIVE] PDF enregistré : %s", destination)
    return destination
