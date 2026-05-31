"""Persistance locale des correspondances mot-clé → produit Leclerc."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import DRIVE_MAPPING_PATH

logger = logging.getLogger(__name__)


def _ensure_parent() -> None:
    DRIVE_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_mapping() -> dict[str, dict[str, Any]]:
    if not DRIVE_MAPPING_PATH.is_file():
        return {}
    try:
        data = json.loads(DRIVE_MAPPING_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Lecture drive_mapping.json en erreur : %s", exc)
    return {}


def _save_mapping(data: dict[str, dict[str, Any]]) -> None:
    _ensure_parent()
    DRIVE_MAPPING_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_mapping(mot_cle: str) -> dict[str, Any] | None:
    key = mot_cle.strip().lower()
    return load_mapping().get(key)


def save_mapping_entry(
    mot_cle: str,
    *,
    product_name: str | None = None,
    product_url: str | None = None,
    product_id: str | None = None,
) -> None:
    key = mot_cle.strip().lower()
    data = load_mapping()
    entry = data.get(key, {})
    if product_name:
        entry["product_name"] = product_name
    if product_url:
        entry["product_url"] = product_url
    if product_id:
        entry["product_id"] = str(product_id)
    data[key] = entry
    _save_mapping(data)
    logger.info("[LeclercBot] Mapping mémorisé : %s → %s", key, entry)


def remove_entry(mot_cle: str) -> None:
    key = mot_cle.strip().lower()
    data = load_mapping()
    if key in data:
        del data[key]
        _save_mapping(data)
        logger.info("[LeclercBot] Mapping supprimé : %s", key)
