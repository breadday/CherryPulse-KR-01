"""Explicit-only WS probe with sanitized output and no account readiness claims."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from adapters.kiwoom_rest_stream import QuoteObservation
from adapters.kiwoom_rest_ws import StreamCapture
from tools.probe_kiwoom_ws import main

if TYPE_CHECKING:
    from pathlib import Path


def quote_view() -> QuoteObservation:
    return QuoteObservation(
        "005930",  # price and clock are fixture evidence, not market data.
        70000,
        "093501",
        datetime(2026, 10, 22, 0, 35, 1),  # noqa: DTZ001 -- Received-at is unused.
        1,
    )


def test_default_is_offline(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert '"network": false' in capsys.readouterr().out


def test_success_is_disconnected_after_capture(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    monkeypatch.setattr(
        "tools.probe_kiwoom_ws.capture_stream",
        lambda *_args, **_kwargs: StreamCapture(
            1, 3, "QUOTE_OBSERVED", fresh_before_close=True, malformed_frames=0
        ),
    )
    assert main(["005930", "--execute-read-only"]) == 0
    output = capsys.readouterr().out
    assert '"connected_after_capture": false' in output
    assert '"account_reconciled": false' in output
    assert "private-secret" not in output


def test_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CHERRYPULSE_PAPER_APP_KEY", raising=False)
    monkeypatch.delenv("KIWOOM_APP_KEY", raising=False)
    assert main(["005930", "--execute-read-only"]) == 1
    assert "SETUP_OR_STREAM_UNCONFIRMED" in capsys.readouterr().out


def test_no_event_is_not_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    monkeypatch.setattr(
        "tools.probe_kiwoom_ws.capture_stream",
        lambda *_args, **_kwargs: StreamCapture(
            1, 0, "NO_QUOTE", fresh_before_close=False, malformed_frames=0
        ),
    )
    assert main(["005930", "--execute-read-only"]) == 1
    assert "NO_QUOTE" in capsys.readouterr().out


def test_quote_out_writes_last_price_without_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    observed = quote_view()
    forbidden_value = "private-token"

    def fake_stream(
        _token: object, _symbols: object, **kwargs: object
    ) -> StreamCapture:
        sink = kwargs.get("quote_sink")
        if callable(sink):
            sink(observed)
        return StreamCapture(
            1, 1, "QUOTE_OBSERVED", fresh_before_close=True, malformed_frames=0
        )

    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", forbidden_value)
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", forbidden_value)
    monkeypatch.setattr("tools.probe_kiwoom_ws.capture_stream", fake_stream)
    destination = tmp_path / "evidence" / "quote.json"
    assert main(["005930", "--execute-read-only", "--quote-out", str(destination)]) == 0
    output = capsys.readouterr().out
    assert '"quote_saved": true' in output
    assert forbidden_value not in output
    book = json.loads(destination.read_text(encoding="utf-8"))
    assert book == {"005930": {"price": 70000, "clock": "093501"}}


def test_invalid_symbol_or_duration_prevents_network(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["bad", "--execute-read-only"]) == 1
    assert "SETUP_OR_STREAM_UNCONFIRMED" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["005930", "--execute-read-only", "--seconds", "121"])
