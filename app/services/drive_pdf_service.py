"""Export PDF planning Menu & Drive — template HTML local + WeasyPrint."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app import config
from app.models.drive import (
    DriveMenuAnalysisResult,
    PlanningRepasItem,
    escape_html,
    ordered_meal_slots,
    parse_meal_slot,
    planning_repas_sort_key,
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
}
thead th {
    background: #166534;
    color: #ffffff;
    font-weight: 600;
    text-align: left;
    padding: 6px 8px;
    font-size: 8pt;
}
tbody td {
    padding: 5px 8px;
    vertical-align: top;
    border-bottom: 1px solid #dcfce7;
    font-size: 8pt;
}
tbody tr:nth-child(even) td { background: #dcfce7; }
tbody tr:nth-child(odd) td { background: #ffffff; }
.col-jour { width: 9%; white-space: nowrap; font-weight: 600; }
.col-plat { width: 12%; }
.col-batch { width: 16%; }
.col-minute { width: 16%; }
"""


def _planning_by_slot(
    items: list[PlanningRepasItem],
) -> dict[tuple[str, str], PlanningRepasItem]:
    indexed: dict[tuple[str, str], PlanningRepasItem] = {}
    for item in items:
        indexed[(item.jour, item.moment)] = item
    return indexed


def _merged_planning_slots(
    result: DriveMenuAnalysisResult,
    *,
    premier_jour: str,
) -> list[tuple[str, str]]:
    enfants = {(item.jour, item.moment) for item in result.planning_repas}
    regime = {(item.jour, item.moment) for item in result.planning_regime}
    all_slots = enfants | regime
    if not all_slots:
        return []
    ordered = []
    for slot in ordered_meal_slots(premier_jour):
        try:
            key = parse_meal_slot(slot)
        except ValueError:
            continue
        if key in all_slots:
            ordered.append(key)
    remaining = sorted(
        all_slots - set(ordered),
        key=lambda key: planning_repas_sort_key(
            PlanningRepasItem(
                jour=key[0],  # type: ignore[arg-type]
                moment=key[1],  # type: ignore[arg-type]
                plat="-",
                batch_cooking_dimanche="-",
                action_minute="-",
            ),
            premier_jour=premier_jour,
        ),
    )
    return ordered + remaining


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
    rows: list[str] = []
    for jour, moment in _merged_planning_slots(result, premier_jour=premier_jour_semaine):
        creneau = f"{escape_html(jour)} {escape_html(moment)}"
        enfant = enfants_by_slot.get((jour, moment))
        hote = regime_by_slot.get((jour, moment))
        rows.append(
            "<tr>"
            f'<td class="col-jour">{creneau}</td>'
            f'<td class="col-plat">{escape_html(enfant.plat if enfant else "")}</td>'
            f'<td class="col-batch">{escape_html(enfant.batch_cooking_dimanche if enfant else "")}</td>'
            f'<td class="col-minute">{escape_html(enfant.action_minute if enfant else "")}</td>'
            f'<td class="col-plat">{escape_html(hote.plat if hote else "")}</td>'
            f'<td class="col-batch">{escape_html(hote.batch_cooking_dimanche if hote else "")}</td>'
            f'<td class="col-minute">{escape_html(hote.action_minute if hote else "")}</td>'
            "</tr>"
        )
    body_rows = "\n".join(rows)
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
  <table>
    <thead>
      <tr>
        <th>Jour</th>
        <th>Plat enfants</th>
        <th>Batch enfants</th>
        <th>Action J enfants</th>
        <th>Plat hôte régime</th>
        <th>Batch hôte</th>
        <th>Action J hôte</th>
      </tr>
    </thead>
    <tbody>
{body_rows}
    </tbody>
  </table>
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
