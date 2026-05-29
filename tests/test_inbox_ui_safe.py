"""Tests garde-fous UI Inbox."""

from unittest.mock import MagicMock

from app.ui.inbox_ui_safe import element_client_alive, safe_clear


def test_element_client_alive_false_when_deleted():
    element = MagicMock()
    element.is_deleted = True
    assert element_client_alive(element) is False


def test_element_client_alive_true_when_connected():
    element = MagicMock()
    element.is_deleted = False
    client = MagicMock()
    client._deleted = False
    client.has_socket_connection = True
    element._client.return_value = client
    assert element_client_alive(element) is True


def test_safe_clear_skips_dead_client():
    element = MagicMock()
    element.is_deleted = True
    assert safe_clear(element) is False
    element.clear.assert_not_called()
