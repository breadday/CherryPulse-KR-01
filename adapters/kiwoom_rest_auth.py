"""In-memory mock authentication; no credential files, repr, or automatic retries."""

# pyright: reportUnnecessaryIsInstance=false, reportUnreachable=false
# Runtime validation deliberately checks untrusted injected responses.

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import TYPE_CHECKING, cast
from urllib.request import HTTPRedirectHandler, Request, build_opener

from typing_extensions import override

if TYPE_CHECKING:
    from _thread import LockType
    from collections.abc import Callable
    from http.client import HTTPResponse

KST = timezone(timedelta(hours=9))
MAX_RESPONSE_BYTES = 1024 * 1024


class PaperAuthError(ValueError):
    """Non-sensitive authentication error; underlying exceptions are suppressed."""


class RequestPacer:
    """Serialize one session's requests using monotonic time, including failures."""

    def __init__(
        self,
        *,
        interval: float = 1.1,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        """Keep a conservative minimum interval, with injectable test timing."""
        if not math.isfinite(interval) or interval < 1:
            raise ValueError("INTERVAL_INVALID")
        self._interval: float = interval
        self._clock: Callable[[], float] = clock
        self._wait: Callable[[float], None] = wait
        self._next: float = 0.0
        self._lock: LockType = Lock()

    def acquire(self) -> None:
        """Wait before a request and reserve the next slot under one lock."""
        with self._lock:
            now = self._clock()
            if now < self._next:
                self._wait(self._next - now)
                now = self._clock()
            self._next = max(now, self._next) + self._interval


@dataclass(frozen=True, slots=True)
class PaperCredentials:
    """Explicit paper-only credentials; values never appear in repr."""

    app_key: str = field(repr=False)
    app_secret: str = field(repr=False)

    def __post_init__(self) -> None:
        """Reject empty values and control characters without echoing secrets."""
        if any(
            not isinstance(value, str)
            or not value.strip()
            or any(char in value for char in "\r\n")
            for value in (self.app_key, self.app_secret)
        ):
            raise PaperAuthError("CREDENTIALS_INVALID")


def paper_credentials_from_env() -> PaperCredentials:
    """Read the user-registered paper keys from the environment, never echoing them."""
    app_key = os.environ.get("CHERRYPULSE_PAPER_APP_KEY") or os.environ.get(
        "KIWOOM_APP_KEY", ""
    )
    app_secret = os.environ.get("CHERRYPULSE_PAPER_APP_SECRET") or os.environ.get(
        "KIWOOM_APP_SECRET", ""
    )
    return PaperCredentials(app_key, app_secret)


class NoAuthRedirect(HTTPRedirectHandler):
    """Prevent token issuance credentials from following redirects."""

    @override
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        """Reject all redirect destinations."""


class PaperTokenIssuer:
    """Issue one token on the fixed mock endpoint without SDK dependencies."""

    def __init__(self, pacer: RequestPacer, *, timeout: float = 10) -> None:
        """Require a bounded finite request timeout."""
        if not math.isfinite(timeout) or not 0 < timeout <= 30:  # noqa: PLR2004
            raise ValueError("TIMEOUT_INVALID")
        self._pacer: RequestPacer = pacer
        self._timeout: float = timeout

    def issue(self, credentials: PaperCredentials) -> dict[str, object]:
        """Return token fields only in memory; never expose raw failures."""
        body = {
            "grant_type": "client_credentials",
            "appkey": credentials.app_key,
            "secretkey": credentials.app_secret,
        }
        request = Request(
            "https://mockapi.kiwoom.com/oauth2/token",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json;charset=UTF-8"},
            method="POST",
        )
        try:
            self._pacer.acquire()
            with cast(
                "HTTPResponse",
                build_opener(NoAuthRedirect()).open(request, timeout=self._timeout),
            ) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except Exception:  # noqa: BLE001 -- Secret-bearing exception strings are unsafe.
            raise PaperAuthError("AUTH_UNCONFIRMED") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise PaperAuthError("AUTH_RESPONSE_TOO_LARGE")
        try:
            payload = cast("object", json.loads(raw))
        except (ValueError, UnicodeError):
            raise PaperAuthError("AUTH_RESPONSE_INVALID") from None
        if not isinstance(payload, dict):
            raise PaperAuthError("AUTH_RESPONSE_INVALID")
        return cast("dict[str, object]", payload)


class PaperTokenCache:
    """Single-flight token renewal; cache is never persisted to disk."""

    def __init__(
        self,
        credentials: PaperCredentials,
        issue: Callable[[PaperCredentials], dict[str, object]],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Keep credentials private and renew one minute before expiry."""
        self._credentials: PaperCredentials = credentials
        self._issue: Callable[[PaperCredentials], dict[str, object]] = issue
        self._now: Callable[[], datetime] = now
        self._token: str | None = None
        self._expires: datetime | None = None
        self._last_now: datetime | None = None
        self._lock: LockType = Lock()

    def get(self) -> str:
        """Fail closed on clock rollback, malformed tokens, or issuance failure."""
        with self._lock:
            now = self._now()
            if now.utcoffset() is None or (
                self._last_now is not None and now < self._last_now
            ):
                self._token = None
                raise PaperAuthError("AUTH_CLOCK_UNCERTAIN")
            self._last_now = now
            if (
                self._token is not None
                and self._expires is not None
                and now + timedelta(minutes=1) < self._expires
            ):
                return self._token
            self._token = None
            try:
                payload = self._issue(self._credentials)
                refreshed_now = self._now()
                token, expiry = parse_token(payload, refreshed_now)
                if refreshed_now < now:
                    raise PaperAuthError("AUTH_CLOCK_UNCERTAIN")  # noqa: TRY301
            except Exception:  # noqa: BLE001 -- Never leak issuer credentials or token.
                raise PaperAuthError("AUTH_UNCONFIRMED") from None
            self._last_now = refreshed_now
            self._token, self._expires = token, expiry
            return token


def parse_token(payload: dict[str, object], now: datetime) -> tuple[str, datetime]:
    """Validate business success, bearer type and explicit KST expiry."""
    code = payload.get("return_code")
    token = payload.get("token")
    expires = payload.get("expires_dt")
    if type(code) not in (int, str) or code not in (0, "0"):
        raise PaperAuthError("AUTH_SUCCESS_UNCONFIRMED")
    token_type = payload.get("token_type")
    if (
        not isinstance(token_type, str)
        or token_type.lower() != "bearer"
        or not isinstance(token, str)
        or not token
        or any(char in token for char in "\r\n")
        or not isinstance(expires, str)
        or len(expires) != 14  # noqa: PLR2004 -- YYYYMMDDHHMMSS format.
        or not expires.isascii()
        or not expires.isdigit()
        or now.utcoffset() is None
    ):
        raise PaperAuthError("TOKEN_INVALID")
    expiry = datetime.strptime(expires, "%Y%m%d%H%M%S").replace(tzinfo=KST)
    if expiry <= now + timedelta(minutes=1):
        raise PaperAuthError("TOKEN_EXPIRED")
    return token, expiry
