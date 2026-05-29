"""Client mock pour tests sans Ollama (spec §5.4)."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.models.analysis import DocumentAnalysisResult, TaskAnalysisItem
from app.utils.analysis_logging import log_analysis_result

logger = logging.getLogger(__name__)


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

    def analyze_document(self, file_path: Path) -> DocumentAnalysisResult:
        result = self._build_mock_analysis(file_path)
        log_analysis_result(
            logger,
            stage="MOCK démo",
            filename=file_path.name,
            result=result,
        )
        return result

    def _build_mock_analysis(self, file_path: Path) -> DocumentAnalysisResult:
        name = file_path.name
        prefix, _, rest = name.partition("_")
        label = rest if len(prefix) == 32 and rest else name
        label = Path(label).stem.replace("_", " ").strip()[:60] or "document"
        today = date.today()

        return DocumentAnalysisResult(
            tasks=[
                TaskAnalysisItem(
                    title=f"Traiter le document : {label}",
                    date_emission=today,
                    deadline=None,
                    category="pro",
                    tags=["aclasser"],
                    confidence=0.3,
                    justification_proof="Aucune",
                )
            ],
            document_summary=(
                f"[DÉMO] Document « {name} » — "
                "installez llama3.2-vision via Ollama pour une analyse réelle."
            ),
            confidence=0.3,
        )
