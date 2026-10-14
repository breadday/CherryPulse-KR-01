"""Bounded paper quote capture with reconnect and no execution-engine imports."""

from __future__ import annotations

import importlib
import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, cast

from adapters.kiwoom_rest_auth import MAX_RESPONSE_BYTES, RequestPacer
from adapters.kiwoom_rest_stream import QuoteStreamState

if TYPE_CHECKING:
    from collections.abc import Callable


class QuoteSocket(Protocol):
    """Minimal socket surface, replaceable by an offline recording fake."""

    def send(self, message: str) -> None:
        """Send a protocol control packet, never a broker order."""
        ...

    def recv(self, *, timeout: float) -> str | bytes:
        """Receive a bounded frame or raise timeout/disconnection."""
        ...

    def close(self) -> None:
        """Close transport even after a protocol or network failure."""
        ...


class ConnectFactory(Protocol):
    """Typed public connection call supported by the pinned websockets version."""

    def __call__(  # noqa: PLR0913 -- Matches public websocket signature.
        self,
        uri: str,
        *,
        open_timeout: float,
        close_timeout: float,
        ping_interval: None,
        max_size: int,
        proxy: None,
        logger: logging.Logger,
    ) -> QuoteSocket:
        """Open a TLS WebSocket with a finite handshake deadline."""
        ...


def connect_paper(*, timeout: float) -> QuoteSocket:
    """Load optional websockets only for an explicitly requested live probe."""
    client = importlib.import_module("websockets.sync.client")
    connect = cast("ConnectFactory", client.connect)
    private_logger = logging.Logger(  # noqa: LOG001 -- Isolated logger prevents host DEBUG token leakage.
        "cherrypulse.paper.ws", level=logging.CRITICAL + 1
    )
    private_logger.propagate = False
    return connect(
        "wss://mockapi.kiwoom.com:10000/api/dostk/websocket",
        open_timeout=timeout,
        close_timeout=2,
        ping_interval=None,
        max_size=MAX_RESPONSE_BYTES,
        proxy=None,
        logger=private_logger,
    )


@dataclass(frozen=True, slots=True)
class StreamCapture:
    """Summary contains no token or raw broker events; capture ends disconnected."""

    connections: int
    quotes_observed: int
    reason: str
    fresh_before_close: bool
    malformed_frames: int
    orders_enabled: bool = False
    account_reconciled: bool = False


def decode_frame(raw: str | bytes) -> object:
    """Support Kiwoom text PING and JSON; reject oversized/invalid frames."""
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("FRAME_TOO_LARGE")
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    if text.strip() == "PING":
        return "PING"
    return cast("object", json.loads(text))


@dataclass(frozen=True, slots=True)
class StreamTiming:
    """Injectable clocks keep protocol tests offline and deterministic."""

    clock: Callable[[], float] = time.monotonic
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


@dataclass(slots=True)
class StreamMetrics:
    """Preserve observed counts when a socket fails mid-stream."""

    quotes: int = 0
    malformed: int = 0


def _pump(
    socket: QuoteSocket,
    state: QuoteStreamState,
    deadline: float,
    timing: StreamTiming,
    metrics: StreamMetrics,
) -> None:
    """Handle control packets and observations within a single connection."""
    clock, now = timing.clock, timing.now
    phase_deadline = min(deadline, clock() + 10)
    while clock() < deadline:
        if not state.registered and clock() >= phase_deadline:
            raise TimeoutError("HANDSHAKE_TIMEOUT")
        try:
            raw = socket.recv(timeout=min(1.0, deadline - clock()))
        except TimeoutError:
            continue
        try:
            frame = decode_frame(raw)
        except (ValueError, UnicodeError):
            metrics.malformed += 1
            continue
        if frame == "PING":
            socket.send("PING")
            continue
        message = cast("dict[str, object]", frame) if isinstance(frame, dict) else {}
        if message.get("trnm") == "PING":
            socket.send(json.dumps(message))
            continue
        was_logged_in = state.logged_in
        observations = state.consume(cast("object", frame), now())
        metrics.quotes += len(observations)
        if not was_logged_in and state.logged_in:
            socket.send(json.dumps(state.registration()))
            phase_deadline = min(deadline, clock() + 10)
        if state.reason in {"LOGIN_REJECTED", "REGISTRATION_REJECTED"}:
            break


def capture_stream(  # noqa: PLR0913 -- Explicit clocks and transports for offline tests.
    token: Callable[[], str],
    symbols: tuple[str, ...],
    *,
    seconds: float,
    reconnects: int = 2,
    connect: Callable[[float], QuoteSocket] | None = None,
    timing: StreamTiming | None = None,
    pacer: RequestPacer | None = None,
) -> StreamCapture:
    """Re-login and re-register after transport loss; never preserve live readiness."""
    if not math.isfinite(seconds) or not 0 < seconds <= 120:  # noqa: PLR2004
        raise ValueError("DURATION_INVALID")
    if type(reconnects) is not int or not 0 <= reconnects <= 3:  # noqa: PLR2004
        raise ValueError("RECONNECT_LIMIT_INVALID")
    state = QuoteStreamState(symbols)
    clocks = timing if timing is not None else StreamTiming()
    clock, now = clocks.clock, clocks.now
    metrics = StreamMetrics()
    gate = pacer if pacer is not None else RequestPacer()

    def default_connect(limit: float) -> QuoteSocket:
        return connect_paper(timeout=limit)

    factory = connect if connect is not None else default_connect
    deadline = clock() + seconds
    connections = 0
    reason = "NO_QUOTE"
    fresh = False
    for _ in range(reconnects + 1):
        socket: QuoteSocket | None = None
        token_ready = False
        try:
            access_token = token()
            if not access_token or any(char in access_token for char in "\r\n"):
                raise ValueError("TOKEN_INVALID")  # noqa: TRY301
            token_ready = True
            gate.acquire()
            remaining = deadline - clock()
            if remaining <= 0:
                break
            socket = factory(min(10.0, remaining))
            state.begin()
            connections += 1
            socket.send(json.dumps({"trnm": "LOGIN", "token": access_token}))
            _pump(socket, state, deadline, clocks, metrics)
            reason = state.reason
            fresh = any(
                state.usable(symbol, now(), max_age_seconds=3) for symbol in symbols
            )
            break
        except Exception:  # noqa: BLE001 -- Do not expose token-bearing exception context.
            reason = "STREAM_UNCONFIRMED"
            fresh = False
            if not token_ready:
                break
        finally:
            if not close_socket(socket):
                reason = "CLOSE_UNCONFIRMED"
                fresh = False
            state.disconnect()
    return StreamCapture(connections, metrics.quotes, reason, fresh, metrics.malformed)


def close_socket(socket: QuoteSocket | None) -> bool:
    """Sanitize close errors and always leave the protocol state disconnected."""
    if socket is None:
        return True
    try:
        socket.close()
    except Exception:  # noqa: BLE001 -- No credential-bearing close traceback.
        return False
    return True
