"""Recording sockets exercise reconnects without credentials or network access."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from adapters.kiwoom_rest_auth import RequestPacer
from adapters.kiwoom_rest_stream import QuoteObservation
from adapters.kiwoom_rest_ws import (
    StreamCapture,
    StreamTiming,
    capture_stream,
    connect_paper,
    decode_frame,
)

START = datetime(2026, 10, 14, tzinfo=timezone.utc)
LOGIN = '{"trnm":"LOGIN","return_code":0}'
REG = '{"trnm":"REG","return_code":0}'
REAL = (
    '{"trnm":"REAL","data":[{"type":"0B","item":"005930",'
    '"values":{"10":"+70000","20":"090501"}}]}'
)


class Clock:
    def __init__(self) -> None:
        self.seconds: float = 0.0

    def clock(self) -> float:
        return self.seconds

    def now(self) -> datetime:
        return START + timedelta(seconds=self.seconds)

    def wait(self, seconds: float) -> None:
        self.seconds += seconds


class Socket:
    def __init__(self, clock: Clock, frames: list[str | Exception]) -> None:
        self.clock: Clock = clock
        self.frames: list[str | Exception] = list(frames)
        self.sent: list[str] = []
        self.closed: bool = False

    def send(self, message: str) -> None:
        self.sent.append(message)

    def recv(self, *, timeout: float) -> str:
        self.clock.wait(min(timeout, 0.25) if self.frames else timeout)
        if not self.frames:
            raise TimeoutError
        frame = self.frames.pop(0)
        if isinstance(frame, Exception):
            raise frame
        return frame

    def close(self) -> None:
        self.closed = True


def run_capture(
    clock: Clock,
    sockets: list[Socket],
    *,
    seconds: float = 4,
    reconnects: int = 2,
    quote_sink: Callable[[QuoteObservation], None] | None = None,
) -> StreamCapture:
    pending = iter(sockets)
    return capture_stream(
        lambda: "synthetic-token",
        ("005930",),
        seconds=seconds,
        reconnects=reconnects,
        connect=lambda _: next(pending),
        timing=StreamTiming(clock.clock, clock.now),
        pacer=RequestPacer(clock=clock.clock, wait=clock.wait),
        quote_sink=quote_sink,
    )


def test_quote_sink_receives_each_observation_in_order() -> None:
    clock = Clock()
    first = Socket(clock, [LOGIN, REG, REAL, OSError("connection lost")])
    second = Socket(clock, [LOGIN, REG, REAL])
    received: list[QuoteObservation] = []
    report = run_capture(clock, [first, second], quote_sink=received.append)
    prices = [quote.price for quote in received]
    generations = [quote.generation for quote in received]
    assert prices == [70000, 70000]
    assert generations == [1, 2]
    assert all(quote.symbol == "005930" for quote in received)
    assert report.quotes_observed == len(received)


def test_login_ping_registration_real_and_cleanup() -> None:
    clock = Clock()
    socket = Socket(clock, ["PING", LOGIN, '{"trnm":"PING"}', REG, REAL])
    report = run_capture(clock, [socket], seconds=3)
    assert report.quotes_observed == 1
    assert report.fresh_before_close
    assert socket.closed
    assert socket.sent[0] == '{"trnm": "LOGIN", "token": "synthetic-token"}'
    assert "PING" in socket.sent
    packets = [json.loads(packet) for packet in socket.sent if packet != "PING"]
    assert [packet["trnm"] for packet in packets] == ["LOGIN", "REG", "PING"]
    assert all(packet["trnm"] in {"LOGIN", "REG", "PING"} for packet in packets)
    assert not report.orders_enabled
    assert not report.account_reconciled
    assert "synthetic-token" not in repr(report)


def test_reconnect_retains_observation_count_and_reregisters() -> None:
    clock = Clock()
    first = Socket(clock, [LOGIN, REG, REAL, OSError("connection lost")])
    second = Socket(clock, [LOGIN, REG, REAL])
    report = run_capture(clock, [first, second])
    assert report.connections == 2
    assert report.quotes_observed == 2
    assert first.closed
    assert second.closed
    for socket in [first, second]:
        packets = [json.loads(packet)["trnm"] for packet in socket.sent]
        assert packets == ["LOGIN", "REG"]


def test_reconnect_without_new_quote_is_not_fresh() -> None:
    clock = Clock()
    first = Socket(clock, [LOGIN, REG, REAL, OSError()])
    second = Socket(clock, [LOGIN, REG])
    report = run_capture(clock, [first, second])
    assert report.quotes_observed == 1
    assert not report.fresh_before_close
    assert report.reason == "NO_QUOTE"


def test_rejected_login_does_not_register_or_retry() -> None:
    clock = Clock()
    socket = Socket(clock, ['{"trnm":"LOGIN","return_code":3}'])
    report = run_capture(clock, [socket])
    assert report.connections == 1
    assert report.reason == "LOGIN_REJECTED"
    assert len(socket.sent) == 1
    assert socket.closed


def test_bad_json_counted_without_using_it_as_a_quote() -> None:
    clock = Clock()
    socket = Socket(clock, [LOGIN, REG, "not json"])
    report = run_capture(clock, [socket])
    assert report.malformed_frames == 1
    assert report.quotes_observed == 0


def test_auth_failure_is_sanitized_without_retry_or_connect() -> None:
    calls: list[int] = []

    def token() -> str:
        calls.append(1)
        raise ValueError("synthetic-token")

    report = capture_stream(token, ("005930",), seconds=1)
    assert calls == [1]
    assert report.connections == 0
    assert report.reason == "STREAM_UNCONFIRMED"
    assert "synthetic-token" not in repr(report)


def test_connection_failures_are_bounded() -> None:
    clock = Clock()
    sockets = [Socket(clock, [OSError()]), Socket(clock, [OSError()])]
    report = run_capture(clock, sockets, reconnects=1)
    assert report.connections == 2
    assert not report.fresh_before_close
    assert all(socket.closed for socket in sockets)


@pytest.mark.parametrize("seconds", [0, 121, float("nan"), float("inf")])
def test_invalid_duration_prevents_auth(seconds: float) -> None:
    with pytest.raises(ValueError, match="DURATION_INVALID"):
        capture_stream(lambda: "unused", ("005930",), seconds=seconds)


def test_optional_client_uses_only_mock_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket = Socket(Clock(), [])
    calls: list[tuple[str, dict[str, object]]] = []

    def connect(uri: str, **options: object) -> Socket:
        calls.append((uri, options))
        return socket

    monkeypatch.setattr(
        "adapters.kiwoom_rest_ws.importlib.import_module",
        lambda _: SimpleNamespace(connect=connect),
    )
    assert connect_paper(timeout=5) is socket
    assert calls[0][0] == "wss://mockapi.kiwoom.com:10000/api/dostk/websocket"
    assert calls[0][1]["proxy"] is None
    assert calls[0][1]["ping_interval"] is None


def test_decode_accepts_bytes_but_not_arbitrary_text() -> None:
    assert decode_frame(b'{"trnm":"PING"}') == {"trnm": "PING"}
    with pytest.raises(ValueError, match="Expecting value"):
        decode_frame("bad json")
