"""Failure context is typed and sanitized without opening a network socket."""

from __future__ import annotations

from datetime import datetime, timezone

from adapters.kiwoom_rest_auth import RequestPacer
from adapters.kiwoom_rest_ws import QuoteSocket, StreamTiming, capture_stream


def test_capture_failure_reports_only_safe_stage_and_kind() -> None:
    tick = 0.0

    def clock() -> float:
        return tick

    def wait(seconds: float) -> None:
        nonlocal tick
        tick += seconds

    cases = [
        ("TOKEN", ValueError("private token detail"), "VALUE_ERROR"),
        ("CONNECT", OSError("private endpoint detail"), "OS_ERROR"),
    ]
    for failed_stage, error, expected_kind in cases:

        def token(
            captured_stage: str = failed_stage, captured_error: Exception = error
        ) -> str:
            if captured_stage == "TOKEN":
                raise captured_error
            return "synthetic-token"

        def connect(_timeout: float, captured_error: Exception = error) -> QuoteSocket:
            raise captured_error

        report = capture_stream(
            token,
            ("005930",),
            seconds=1,
            reconnects=0,
            connect=connect,
            timing=StreamTiming(clock, lambda: datetime.now(timezone.utc)),
            pacer=RequestPacer(clock=clock, wait=wait),
        )

        assert report.failure_stage == failed_stage
        assert report.failure_kind == expected_kind
        assert "private" not in repr(report)
        assert "synthetic-token" not in repr(report)
