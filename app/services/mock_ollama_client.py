"""Client mock pour tests sans Ollama (spec §5.4)."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.models.analysis import DocumentAnalysis

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = ""  # non utilisé en mock


class MockOllamaClient:
    """Renvoie un JSON simulé valide lorsque Ollama est indisponible."""

    is_mock: bool = True

    def __init__(self) -> None:
        logger.warning(
            "Mode démo actif — Ollama non disponible. "
            "Les champs sont pré-remplis avec des données simulées."
        )

    @property
    def warning_message(self) -> str:
        return "Mode démo — Ollama non disponible. Données simulées."

    def is_available(self) -> bool:
        return False

    def analyze_document(self, file_path: Path) -> DocumentAnalysis:
        return self._build_mock_analysis(file_path)

    def _build_mock_analysis(self, file_path: Path) -> DocumentAnalysis:
        stem = file_path.stem.replace("_", " ")
        suffix = file_path.suffix.lower()
        today = date.today()

        if "urssaf" in stem.lower() or "cotisation" in stem.lower():
            return DocumentAnalysis(
                title="Envoyer la déclaration URSSAF",
                date_emission=today,
                deadline=None,
                category="pro",
                tags=["Compta", "URSSAF"],
                confidence=0.4,
                raw_summary=f"[DÉMO] Courrier administratif détecté depuis « {file_path.name} ».",
            )

        if "expo" in stem.lower() or suffix in {".png", ".jpg", ".jpeg", ".heic"}:
            return DocumentAnalysis(
                title="Mettre à jour le SDK Expo",
                date_emission=today,
                deadline=None,
                category="pro",
                tags=["Tech", "Expo", "Maintenance"],
                confidence=0.4,
                raw_summary=(
                    f"[DÉMO] Capture d'écran analysée (simulation) — fichier « {file_path.name} »."
                ),
            )

        doc_type = "PDF" if suffix == ".pdf" else "image"
        return DocumentAnalysis(
            title=f"Traiter le document : {stem[:60]}",
            date_emission=today,
            deadline=None,
            category="pro",
            tags=["À classer"],
            confidence=0.3,
            raw_summary=(
                f"[DÉMO] Document {doc_type} « {file_path.name} » — "
                "installez llama3.2-vision via Ollama pour une analyse réelle."
            ),
        )
