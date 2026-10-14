"""Deny real socket connections in all offline REST tests."""

import pytest


def deny_connection(*_args: object, **_kwargs: object) -> None:
    """Catch accidental network access before it leaves the test process."""
    raise RuntimeError("OFFLINE_TEST_NETWORK_FORBIDDEN")


@pytest.fixture(autouse=True)
def offline_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Require every network operation to use explicit fake transports."""
    monkeypatch.setattr("socket.socket.connect", deny_connection)
    monkeypatch.setattr("socket.create_connection", deny_connection)
