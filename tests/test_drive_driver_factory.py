"""Tests factory robots Drive."""

import pytest

from app.services.drive_driver_factory import create_drive_driver


def test_create_leclerc_driver():
    driver = create_drive_driver(
        "leclerc",
        on_status=lambda _m: None,
        on_failures=lambda _p: None,
    )
    assert driver.platform_id == "leclerc"


def test_create_unavailable_platform_raises():
    with pytest.raises(RuntimeError, match="Bientôt"):
        create_drive_driver(
            "auchan",
            on_status=lambda _m: None,
            on_failures=lambda _p: None,
        )
