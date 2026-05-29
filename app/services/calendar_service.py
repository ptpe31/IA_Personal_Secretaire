"""Intégration Google Calendar — spec §10."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from app.config import CREDENTIALS_PATH
from app.db.connection import get_setting
from app.models.task import TaskDTO

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CREDENTIALS_FILE = CREDENTIALS_PATH / "credentials.json"
TOKEN_FILE = CREDENTIALS_PATH / "token.json"

_MONTHS_FR = (
    "",
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
)


def format_deadline_label(deadline: date) -> str:
    return f"{deadline.day} {_MONTHS_FR[deadline.month]}"


def build_event_title(task: TaskDTO) -> str:
    prefix = "PRO" if task.category == "pro" else "PERSO"
    if task.deadline:
        limit = format_deadline_label(task.deadline)
        return f"[{prefix}] {task.title} (Limite: {limit})"
    return f"[{prefix}] {task.title}"


def build_event_description(task: TaskDTO) -> str:
    from app.utils.dates import format_date_fr

    tags = ", ".join(f"#{t}" for t in task.tags) if task.tags else "—"
    return (
        f"Document reçu le {format_date_fr(task.date_emission)}. "
        f"Tags associés : {tags}."
    )


class CalendarService:
    """Sync manuelle vers Google Calendar (primary)."""

    def __init__(self) -> None:
        CREDENTIALS_PATH.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def has_credentials_file() -> bool:
        return CREDENTIALS_FILE.is_file()

    @staticmethod
    def has_token() -> bool:
        return TOKEN_FILE.is_file()

    def is_configured(self) -> bool:
        return self.has_credentials_file()

    def is_authenticated(self) -> bool:
        if not self.is_configured():
            return False
        try:
            creds = self._load_credentials()
            return creds is not None and creds.valid
        except Exception:
            return False

    def _load_credentials(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if TOKEN_FILE.is_file():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

        if creds and creds.valid:
            return creds

        if not self.is_configured():
            return None

        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def _calendar_api(self):
        from googleapiclient.discovery import build

        creds = self._load_credentials()
        if creds is None:
            raise RuntimeError("Authentification Google Calendar requise.")
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def authorize(self) -> None:
        """Lance le flux OAuth (ouvre le navigateur)."""
        if not self.is_configured():
            raise FileNotFoundError(
                f"Placez credentials.json dans {CREDENTIALS_PATH}"
            )
        self._load_credentials()

    def sync_task(self, task: TaskDTO) -> str:
        """Crée un événement all-day à la deadline. Retourne l'ID Google."""
        if task.deadline is None:
            raise ValueError("Impossible de synchroniser une tâche sans deadline.")
        if task.calendar_synced and task.calendar_event_id:
            return task.calendar_event_id

        service = self._calendar_api()
        end_date = task.deadline + timedelta(days=1)
        event_body = {
            "summary": build_event_title(task),
            "description": build_event_description(task),
            "start": {"date": task.deadline.isoformat()},
            "end": {"date": end_date.isoformat()},
        }
        created = (
            service.events()
            .insert(calendarId="primary", body=event_body)
            .execute()
        )
        event_id = str(created["id"])

        from app.services.task_service import mark_calendar_synced

        mark_calendar_synced(task.id, event_id)
        logger.info("Tâche %s synchronisée — événement %s", task.id, event_id)
        return event_id


def is_auto_sync_enabled() -> bool:
    return get_setting("google_calendar_auto_sync", "false") == "true"


def try_auto_sync_task(task_id: int) -> bool:
    """Sync auto si activée et credentials OK. Retourne True si sync effectuée."""
    if not is_auto_sync_enabled():
        return False
    calendar = CalendarService()
    if not calendar.is_configured():
        return False
    try:
        from app.services.task_service import get_task_by_id

        task = get_task_by_id(task_id)
        if task is None or task.deadline is None:
            return False
        calendar.sync_task(task)
        return True
    except Exception as exc:
        logger.warning("Sync auto Calendar échouée pour tâche %s : %s", task_id, exc)
        return False
