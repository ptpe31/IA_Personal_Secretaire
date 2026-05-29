"""Tests relances J-3 / J-1."""

from datetime import date

from app.services.notification_service import (
    build_reminder_message,
    days_until_deadline,
    notification_type_for_days,
)


def test_days_until_deadline():
    today = date(2026, 5, 29)
    assert days_until_deadline(date(2026, 6, 1), today) == 3
    assert days_until_deadline(date(2026, 5, 30), today) == 1


def test_notification_type_j3_j1_only():
    assert notification_type_for_days(3) == "j_minus_3"
    assert notification_type_for_days(1) == "j_minus_1"
    assert notification_type_for_days(0) is None
    assert notification_type_for_days(7) is None


def test_build_reminder_message_singular():
    assert "1 jour" in build_reminder_message("Expo", 1)
