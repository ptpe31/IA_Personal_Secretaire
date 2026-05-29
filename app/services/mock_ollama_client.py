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
        stem = file_path.stem.replace("_", " ").lower()
        suffix = file_path.suffix.lower()
        today = date.today()

        if any(k in stem for k in ("hip", "culture", "danse", "hop")):
            return self._hiphop_pack(today, file_path.name)

        if "urssaf" in stem or "cotisation" in stem:
            return DocumentAnalysisResult(
                tasks=[
                    TaskAnalysisItem(
                        title="Envoyer la déclaration URSSAF",
                        date_emission=today,
                        deadline=None,
                        category="pro",
                        tags=["compta", "urssaf"],
                        confidence=0.4,
                        justification_proof="Aucune",
                    )
                ],
                document_summary=f"[DÉMO] Courrier administratif détecté depuis « {file_path.name} ».",
                confidence=0.4,
            )

        if "expo" in stem or suffix in {".png", ".jpg", ".jpeg", ".heic"}:
            return DocumentAnalysisResult(
                tasks=[
                    TaskAnalysisItem(
                        title="Mettre à jour le SDK Expo",
                        date_emission=today,
                        deadline=None,
                        category="pro",
                        tags=["tech", "expo", "maintenance"],
                        confidence=0.4,
                        justification_proof="Aucune",
                    )
                ],
                document_summary=(
                    f"[DÉMO] Capture d'écran analysée (simulation) — fichier « {file_path.name} »."
                ),
                confidence=0.4,
            )

        doc_type = "PDF" if suffix == ".pdf" else "image"
        return DocumentAnalysisResult(
            tasks=[
                TaskAnalysisItem(
                    title=f"Traiter le document : {stem[:60]}",
                    date_emission=today,
                    deadline=None,
                    category="pro",
                    tags=["aclasser"],
                    confidence=0.3,
                    justification_proof="Aucune",
                )
            ],
            document_summary=(
                f"[DÉMO] Document {doc_type} « {file_path.name} » — "
                "installez llama3.2-vision via Ollama pour une analyse réelle."
            ),
            confidence=0.3,
        )

    @staticmethod
    def _hiphop_pack(today: date, filename: str) -> DocumentAnalysisResult:
        """Pack démo 5 tâches — mail service culturel hip-hop."""
        emission = date(2026, 5, 26)
        rehearsals = [
            (1, date(2026, 6, 4), "le 4 juin de 18h à 19h"),
            (2, date(2026, 6, 11), "le 11 juin de 18h à 19h"),
            (3, date(2026, 6, 18), "le 18 juin de 18h à 19h"),
            (4, date(2026, 6, 25), "le 25 juin de 18h à 19h"),
        ]
        tasks: list[TaskAnalysisItem] = []
        for index, event_date, proof in rehearsals:
            tasks.append(
                TaskAnalysisItem(
                    title=f"Répétition Hip-Hop {index}/4",
                    date_emission=emission,
                    date_event=event_date,
                    deadline=event_date,
                    category="perso",
                    tags=["enfants", "danse", "hiphop", "repetition"],
                    confidence=0.75,
                    justification_proof=(
                        f"les répétitions qui auront lieu à la salle de cours {proof}"
                    ),
                    suggestion="Horaires de l'atelier : 18h à 19h",
                )
            )
        tasks.append(
            TaskAnalysisItem(
                title="Spectacle de fin d'année Hip-Hop",
                date_emission=emission,
                date_event=date(2026, 6, 27),
                deadline=date(2026, 6, 27),
                category="perso",
                tags=["spectacle", "enfants", "danse", "hiphop"],
                confidence=0.8,
                justification_proof="samedi 27 juin 2026 à l'Astrolab' – place Charles Trenet",
                suggestion="Faire l'inscription par mail ou au 05.62.11.62.66",
            )
        )
        return DocumentAnalysisResult(
            tasks=tasks,
            document_summary=(
                f"[DÉMO] Mail service culturel hip-hop — 5 événements détectés "
                f"dans « {filename} »."
            ),
            confidence=0.75,
        )
