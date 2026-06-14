"""Tests factory robots Drive."""

import pytest

from app.services.chronodrive_driver import ChronodriveDriver
from app.services.drive_driver_factory import create_drive_driver
from app.services.leclerc_driver import LeclercDriver


def test_create_leclerc_driver():
    driver = create_drive_driver(
        "leclerc",
        on_status=lambda _m: None,
        on_failures=lambda _p: None,
    )
    assert isinstance(driver, LeclercDriver)
    assert driver.platform_id == "leclerc"


def test_create_chronodrive_driver():
    driver = create_drive_driver(
        "chronodrive",
        on_status=lambda _m: None,
        on_failures=lambda _p: None,
    )
    assert isinstance(driver, ChronodriveDriver)
    assert driver.platform_id == "chronodrive"


def test_create_unknown_platform_raises():
    with pytest.raises(RuntimeError, match="Aucun driver implémenté"):
        create_drive_driver(
            "unknown",  # type: ignore[arg-type]
            on_status=lambda _m: None,
            on_failures=lambda _p: None,
        )
