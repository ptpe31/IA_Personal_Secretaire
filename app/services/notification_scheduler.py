"""Planificateur de relances en arrière-plan — spec §8.1."""

from __future__ import annotations

import logging
import threading

from app.services.notification_service import process_deadline_reminders

logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = 30 * 60
_started = False


def _run_loop(interval_seconds: int) -> None:
    while True:
        try:
            count = process_deadline_reminders()
            if count:
                logger.info("%s notification(s) de relance envoyée(s).", count)
        except Exception:
            logger.exception("Erreur lors du traitement des relances")
        threading.Event().wait(interval_seconds)


def start_notification_scheduler(*, interval_seconds: int = _INTERVAL_SECONDS) -> None:
    """Démarre le thread daemon de relances (app ouverte uniquement, V1)."""
    global _started
    if _started:
        return
    _started = True

    def initial_check() -> None:
        try:
            process_deadline_reminders()
        except Exception:
            logger.exception("Erreur relance initiale")

    threading.Timer(5.0, initial_check).start()
    thread = threading.Thread(
        target=_run_loop,
        args=(interval_seconds,),
        daemon=True,
        name="trankil-notifications",
    )
    thread.start()
    logger.info("Planificateur de relances démarré (intervalle %ss).", interval_seconds)
