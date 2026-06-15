"""Persistance locale des correspondances mot-clé → produit par enseigne."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.config import DRIVE_MAPPING_PATH
from app.models.drive import DEFAULT_DRIVE_PLATFORM, DrivePlatformId, UniteMesureType

logger = logging.getLogger(__name__)

_PRODUCT_ID_URL_RE = re.compile(r"/(?:ajout|produit|product|fiche-produits)[-/]?(\d+)", re.I)
_PRODUCT_ID_QUERY_RE = re.compile(r"[?&](?:productId|id|codeArticle)=(\d+)", re.I)
_CHRONODRIVE_PRODUCT_ID_RE = re.compile(r"-P(\d+)$", re.I)

_STORE_FIELD_KEYS = frozenset(
    {
        "product_name",
        "product_url",
        "product_id",
        "contenance_paquet",
        "quantite_paquet",
        "unite_paquet",
    }
)


def normalize_product_url(url: str) -> str:
    """Retire fragment (#plus), espaces et slash final pour stockage."""
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    without_fragment = parsed._replace(fragment="")
    normalized = urlunparse(without_fragment).rstrip("/")
    return normalized


def ensure_plus_url(url: str) -> str:
    """URL fiche produit suffixée par #plus pour ajout automatique Leclerc."""
    base = normalize_product_url(url)
    if not base:
        return ""
    return f"{base}#plus"


def extract_product_id(url: str) -> str | None:
    """Extrait un identifiant produit depuis une URL drive (Leclerc ou Chronodrive)."""
    normalized = normalize_product_url(url)
    chronodrive_match = _CHRONODRIVE_PRODUCT_ID_RE.search(normalized)
    if chronodrive_match:
        return chronodrive_match.group(1)
    for pattern in (_PRODUCT_ID_URL_RE, _PRODUCT_ID_QUERY_RE):
        match = pattern.search(normalized)
        if match:
            return match.group(1)
    return None


def is_chronodrive_product_fiche(url: str) -> bool:
    """True si l'URL ressemble à une fiche produit Chronodrive (suffixe -P{id})."""
    lower = normalize_product_url(url).lower()
    if "chronodrive.com" not in lower:
        return False
    if any(token in lower for token in ("recherche", "search", "magasins-chronodrive")):
        return False
    return bool(_CHRONODRIVE_PRODUCT_ID_RE.search(lower))


def is_leclerc_product_fiche(url: str) -> bool:
    """True si l'URL ressemble à une fiche produit Leclerc (hors recherche)."""
    lower = normalize_product_url(url).lower()
    if "leclercdrive" not in lower:
        return False
    if any(token in lower for token in ("recherche", "search", "magasin-103101")):
        if "fiche" not in lower and "produit" not in lower:
            return False
    markers = ("fiche-produits", "fiche_produits", "/produit/", "/product/", "codearticle=")
    return any(marker in lower for marker in markers)


def _ensure_parent() -> None:
    DRIVE_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)


def _is_legacy_flat_entry(entry: dict[str, Any]) -> bool:
    return bool(entry.keys() & _STORE_FIELD_KEYS)


def _normalize_product_entry(entry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Accepte une entrée plate (legacy) ou multi-enseigne."""
    if not entry:
        return {}
    if _is_legacy_flat_entry(entry):
        return {DEFAULT_DRIVE_PLATFORM: dict(entry)}
    stores: dict[str, dict[str, Any]] = {}
    for key, value in entry.items():
        if isinstance(value, dict) and value.keys() & _STORE_FIELD_KEYS:
            stores[key] = dict(value)
    return stores


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


def get_product_entry(mot_cle: str) -> dict[str, dict[str, Any]] | None:
    key = mot_cle.strip().lower()
    raw = load_mapping().get(key)
    if not raw:
        return None
    stores = _normalize_product_entry(raw)
    return stores or None


def get_store_mapping(
    mot_cle: str,
    platform: DrivePlatformId = DEFAULT_DRIVE_PLATFORM,
) -> dict[str, Any] | None:
    stores = get_product_entry(mot_cle)
    if not stores:
        logger.debug("[DriveMapping] %r @ %s → aucune entrée", mot_cle, platform)
        return None
    entry = stores.get(platform)
    if entry:
        logger.debug(
            "[DriveMapping] %r @ %s → url=%s",
            mot_cle,
            platform,
            (str(entry.get("product_url") or "")[:80] or "(vide)"),
        )
    else:
        logger.debug(
            "[DriveMapping] %r @ %s → absent (disponible: %s)",
            mot_cle,
            platform,
            list(stores.keys()),
        )
    return entry


def get_mapping(mot_cle: str) -> dict[str, Any] | None:
    """Rétrocompatibilité — retourne le mapping Leclerc par défaut."""
    return get_store_mapping(mot_cle, DEFAULT_DRIVE_PLATFORM)


def save_mapping_entry(
    mot_cle: str,
    *,
    platform: DrivePlatformId = DEFAULT_DRIVE_PLATFORM,
    product_name: str | None = None,
    product_url: str | None = None,
    product_id: str | None = None,
    contenance_paquet: float | None = None,
    unite_paquet: UniteMesureType | None = None,
    quantite_paquet: float | None = None,
) -> None:
    key = mot_cle.strip().lower()
    data = load_mapping()
    raw = data.get(key, {})
    stores = _normalize_product_entry(raw if isinstance(raw, dict) else {})
    entry = dict(stores.get(platform, {}))

    if product_name:
        entry["product_name"] = product_name
    if product_url:
        entry["product_url"] = normalize_product_url(product_url)
    if product_id:
        entry["product_id"] = str(product_id)
    elif product_url:
        extracted = extract_product_id(product_url)
        if extracted:
            entry["product_id"] = extracted
    if contenance_paquet is not None and contenance_paquet > 0:
        entry["contenance_paquet"] = float(contenance_paquet)
    elif quantite_paquet is not None and quantite_paquet > 0:
        entry["contenance_paquet"] = float(quantite_paquet)
    if unite_paquet is not None:
        entry["unite_paquet"] = unite_paquet

    stores[platform] = entry
    data[key] = stores
    _save_mapping(data)
    logger.info("[DriveBot:%s] Mapping mémorisé : %s → %s", platform, key, entry)


def remove_entry(mot_cle: str, *, platform: DrivePlatformId | None = None) -> None:
    key = mot_cle.strip().lower()
    data = load_mapping()
    raw = data.get(key)
    if not raw:
        return
    if platform is None:
        del data[key]
        _save_mapping(data)
        logger.info("[DriveBot] Mapping supprimé : %s", key)
        return
    stores = _normalize_product_entry(raw)
    stores.pop(platform, None)
    if stores:
        data[key] = stores
    else:
        del data[key]
    _save_mapping(data)
    logger.info("[DriveBot:%s] Mapping supprimé : %s", platform, key)
