"""Tests résolution du port d'écoute NiceGUI."""

import socket

import pytest

from app.config import is_port_available, resolve_listen_port


def test_is_port_available_detects_occupied_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        occupied = blocker.getsockname()[1]
        assert is_port_available(occupied, host="127.0.0.1") is False


def test_resolve_listen_port_falls_back_when_preferred_is_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", 0))
        preferred = sock.getsockname()[1]

        monkeypatch.delenv("TRANKIL_PORT", raising=False)
        monkeypatch.delenv("APP_PORT", raising=False)

        port = resolve_listen_port(preferred=preferred, max_attempts=10)
        assert port != preferred
        assert is_port_available(port) is True


def test_resolve_listen_port_honors_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        env_port = sock.getsockname()[1]

    monkeypatch.setenv("TRANKIL_PORT", str(env_port))
    assert resolve_listen_port() == env_port
