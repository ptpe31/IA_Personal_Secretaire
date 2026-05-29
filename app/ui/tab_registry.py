"""Registre de rafraîchissement des onglets NiceGUI."""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_handlers: dict[str, Callable[[], None]] = {}


def register_tab_refresh(tab_key: str, handler: Callable[[], None]) -> None:
    _handlers[tab_key] = handler


def refresh_tab(tab_key: str) -> None:
    handler = _handlers.get(tab_key)
    if handler is None:
        return
    try:
        handler()
    except Exception:
        logger.exception("Rafraîchissement onglet %s en erreur", tab_key)
