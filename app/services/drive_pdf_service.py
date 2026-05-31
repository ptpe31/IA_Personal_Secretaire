"""Export PDF planning Menu & Drive — template HTML local + WeasyPrint."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app import config
from app.models.drive import DriveMenuAnalysisResult, escape_html, sort_planning_repas
from app.utils.slugify import build_ged_filename, unique_path

logger = logging.getLogger(__name__)

_WEASYPRINT_HINT = (
    "WeasyPrint nécessite les bibliothèques système Homebrew. "
    "Installez : brew install pango gdk-pixbuf libffi "
    "et lancez via start.command (DYLD_FALLBACK_LIBRARY_PATH)."
)

_PLANNING_CSS = """
@page { size: A4; margin: 14mm; }
body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 11pt;
    color: #14532d;
    background: #f0fdf4;
    margin: 0;
    padding: 0;
}
h1 {
    font-size: 18pt;
    color: #166534;
    margin: 0 0 8px 0;
}
.meta {
    font-size: 10pt;
    color: #166534;
    margin: 0 0 16px 0;
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
    padding: 8px 10px;
    font-size: 10pt;
}
tbody td {
    padding: 7px 10px;
    vertical-align: top;
    border-bottom: 1px solid #dcfce7;
    font-size: 10pt;
}
tbody tr:nth-child(even) td { background: #dcfce7; }
tbody tr:nth-child(odd) td { background: #ffffff; }
.col-jour { width: 14%; white-space: nowrap; font-weight: 600; }
.col-plat { width: 22%; }
.col-batch { width: 32%; }
.col-minute { width: 32%; }
"""


def render_planning_html(
    result: DriveMenuAnalysisResult,
    *,
    semaine_label: str,
    nb_convives_enfants: int = 4,
    nb_convives_regime: int = 4,
) -> str:
    """Assemble le HTML imprimable à partir des données structurées (sans IA)."""
    rows: list[str] = []
    for item in sort_planning_repas(result.planning_repas):
        creneau = f"{escape_html(item.jour)} {escape_html(item.moment)}"
        rows.append(
            "<tr>"
            f'<td class="col-jour">{creneau}</td>'
            f'<td class="col-plat">{escape_html(item.plat)}</td>'
            f'<td class="col-batch">{escape_html(item.batch_cooking_dimanche)}</td>'
            f'<td class="col-minute">{escape_html(item.action_minute)}</td>'
            "</tr>"
        )
    body_rows = "\n".join(rows)
    meta = (
        f"Convives enfants : {nb_convives_enfants} | "
        f"Convives régime/extras : {nb_convives_regime} | "
        "Régime pris en compte"
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
        <th>Plat</th>
        <th>Batch Cooking (Dimanche)</th>
        <th>Action Minute</th>
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
    title: str = "Planning_Batch_Cooking",
) -> Path:
    """Génère le HTML localement puis exporte le PDF vers ~/Trankil-v2/Perso/GED/."""
    html = render_planning_html(
        result,
        semaine_label=semaine_label,
        nb_convives_enfants=nb_convives_enfants,
        nb_convives_regime=nb_convives_regime,
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
