"""Persistance de l'état UI Menu & Drive (~/Trankil-v2/current_menu.json)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import CURRENT_MENU_PATH
from app.models.drive import DriveMenuAnalysisResult

logger = logging.getLogger(__name__)


def load_drive_ui_state() -> dict[str, Any] | None:
    if not CURRENT_MENU_PATH.is_file():
        return None
    try:
        data = json.loads(CURRENT_MENU_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Impossible de lire current_menu.json : %s", exc)
        return None


def save_drive_ui_state(payload: dict[str, Any]) -> None:
    try:
        CURRENT_MENU_PATH.parent.mkdir(parents=True, exist_ok=True)
        CURRENT_MENU_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Impossible d'écrire current_menu.json : %s", exc)


def parse_saved_analysis(data: dict[str, Any]) -> DriveMenuAnalysisResult | None:
    raw = data.get("analysis_result")
    if not raw:
        return None
    try:
        return DriveMenuAnalysisResult.model_validate(raw)
    except Exception as exc:
        logger.warning("analysis_result invalide dans current_menu.json : %s", exc)
        return None
