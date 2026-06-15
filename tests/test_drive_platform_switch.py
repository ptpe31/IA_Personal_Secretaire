"""Tests diagnostic changement de plateforme Drive."""

from types import SimpleNamespace

from app.models.drive import platform_id_from_label
from app.ui.drive_view import platform_label_from_event, url_platform_hint


def test_platform_label_from_event_quasar_dict():
    """Quasar q-select renvoie {value: index, label: libellé}."""
    event = SimpleNamespace(
        args={"value": 1, "label": "Chronodrive (Portet)"},
        value=None,
        sender=None,
    )
    assert platform_label_from_event(event) == "Chronodrive (Portet)"
    assert platform_id_from_label(platform_label_from_event(event)) == "chronodrive"


def test_platform_label_from_event_args_string():
    event = SimpleNamespace(args="Chronodrive (Portet)", value=None, sender=None)
    assert platform_label_from_event(event) == "Chronodrive (Portet)"
    assert platform_id_from_label(platform_label_from_event(event)) == "chronodrive"


def test_platform_label_from_event_value():
    event = SimpleNamespace(value="Leclerc Drive", args=None, sender=None)
    assert platform_label_from_event(event) == "Leclerc Drive"
    assert platform_id_from_label(platform_label_from_event(event)) == "leclerc"


def test_platform_label_from_event_index_only():
    event = SimpleNamespace(args={"value": 0}, value=None, sender=None)
    assert platform_label_from_event(event) == "Leclerc Drive"


def test_platform_label_from_event_string_fallback():
    assert platform_label_from_event("Chronodrive (Portet)") == "Chronodrive (Portet)"


def test_url_platform_hint():
    assert url_platform_hint("https://fd4-courses.leclercdrive.fr/x") == "leclerc"
    assert url_platform_hint("https://www.chronodrive.com/foo-P123") == "chronodrive"
    assert url_platform_hint("") == "vide"
