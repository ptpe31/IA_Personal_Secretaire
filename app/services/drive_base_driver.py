"""Interface commune des robots Drive (Leclerc, Auchan, …)."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable

from app.models.drive import DrivePlatformId, DriveShoppingItem


class BaseDriveDriver(ABC):
    """Contrat minimal pour un robot de courses en ligne."""

    platform_id: DrivePlatformId

    def __init__(
        self,
        on_status: Callable[[str], None],
        on_failures: Callable[[list[str]], None],
        on_learned: Callable[[str, str], None] | None = None,
    ) -> None:
        self.on_status = on_status
        self.on_failures = on_failures
        self.on_learned = on_learned or (lambda _mot, _url: None)
        self.resume_event = asyncio.Event()
        self.skip_learning_event = asyncio.Event()
        self.learning_done = asyncio.Event()

    @abstractmethod
    async def run(self, items: list[DriveShoppingItem]) -> None:
        """Lance le robot sur la liste d'articles sélectionnés."""

    async def signal_resume(self) -> None:
        self.resume_event.set()

    async def signal_skip_learning(self) -> None:
        self.skip_learning_event.set()
        self.learning_done.set()
