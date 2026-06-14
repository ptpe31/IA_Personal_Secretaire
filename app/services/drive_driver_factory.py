"""Instanciation dynamique des robots Drive par enseigne."""

from __future__ import annotations

from collections.abc import Callable

from app.models.drive import DRIVE_PLATFORMS, DEFAULT_DRIVE_PLATFORM, DrivePlatformId
from app.services.chronodrive_driver import ChronodriveDriver
from app.services.drive_base_driver import BaseDriveDriver
from app.services.leclerc_driver import LeclercDriver


def create_drive_driver(
    platform: DrivePlatformId,
    *,
    on_status: Callable[[str], None],
    on_failures: Callable[[list[str]], None],
    on_learned: Callable[[str, str], None] | None = None,
) -> BaseDriveDriver:
    cfg = DRIVE_PLATFORMS.get(platform, DRIVE_PLATFORMS[DEFAULT_DRIVE_PLATFORM])
    if not cfg.get("available"):
        raise RuntimeError(f"La plateforme « {cfg['label']} » n'est pas encore disponible.")
    if platform == "leclerc":
        return LeclercDriver(on_status=on_status, on_failures=on_failures, on_learned=on_learned)
    if platform == "chronodrive":
        return ChronodriveDriver(
            on_status=on_status,
            on_failures=on_failures,
            on_learned=on_learned,
        )
    raise RuntimeError(f"Aucun driver implémenté pour la plateforme « {platform} ».")
