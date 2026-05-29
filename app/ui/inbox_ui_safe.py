"""Garde-fous NiceGUI — éviter les manipulations UI sur client déconnecté."""

from __future__ import annotations

import logging

from nicegui import ui

logger = logging.getLogger(__name__)


def element_client_alive(element: ui.element) -> bool:
    """Vérifie que l'élément appartient à un client NiceGUI encore connecté."""
    if element.is_deleted:
        return False
    client = element._client()
    if client is None or client._deleted:
        return False
    return client.has_socket_connection


def safe_clear(element: ui.element) -> bool:
    """Vide un conteneur uniquement si le client est encore actif."""
    if not element_client_alive(element):
        return False
    try:
        element.clear()
        return True
    except RuntimeError:
        return False


def run_if_client_alive(anchor: ui.element, callback, *, on_dead=None) -> None:
    """Exécute un callback UI si le client est connecté ; sinon nettoie."""
    if not element_client_alive(anchor):
        if on_dead:
            on_dead()
        return
    try:
        callback()
    except RuntimeError as exc:
        if "client this element belongs to has been deleted" in str(exc).lower():
            logger.debug("Client NiceGUI déconnecté — callback UI ignoré.")
            if on_dead:
                on_dead()
            return
        raise
