"""Token renewal, secrecy, timing, and issuance contract tests."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.request import HTTPRedirectHandler, Request

import pytest

from adapters.kiwoom_rest_auth import (
    PaperAuthError,
    PaperCredentials,
    PaperTokenCache,
    PaperTokenIssuer,
    RequestPacer,
    paper_credentials_from_env,
    parse_token,
)

START = datetime(2026, 10, 14, tzinfo=timezone.utc)
KEYS = PaperCredentials("secret-key", "secret-value")


def token_payload(**patch: object) -> dict[str, object]:
    result: dict[str, object] = {
        "return_code": 0,
        "token": "private-token",
        "token_type": "bearer",
        "expires_dt": "20261014100000",
    }
    result.update(patch)
    return result


def test_credentials_repr_never_exposes_values() -> None:
    assert "secret-key" not in repr(KEYS)
    assert "secret-value" not in repr(KEYS)


@pytest.mark.parametrize("value", ["", " ", "x\ny", "x\ry"])
def test_invalid_credentials_are_not_echoed(value: str) -> None:
    with pytest.raises(PaperAuthError, match="CREDENTIALS_INVALID"):
        PaperCredentials(value, "private")


def test_env_fallback_prefers_cherrypulse_names_then_kiwoom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHERRYPULSE_PAPER_APP_KEY", raising=False)
    monkeypatch.delenv("CHERRYPULSE_PAPER_APP_SECRET", raising=False)
    monkeypatch.delenv("KIWOOM_APP_KEY", raising=False)
    monkeypatch.delenv("KIWOOM_APP_SECRET", raising=False)
    with pytest.raises(PaperAuthError, match="CREDENTIALS_INVALID"):
        paper_credentials_from_env()
    monkeypatch.setenv("KIWOOM_APP_KEY", "fallback-key")
    monkeypatch.setenv("KIWOOM_APP_SECRET", "fallback-secret")
    fallback = paper_credentials_from_env()
    assert fallback.app_key == os.environ["KIWOOM_APP_KEY"]
    assert fallback.app_secret == os.environ["KIWOOM_APP_SECRET"]
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "primary-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "primary-secret")
    primary = paper_credentials_from_env()
    assert primary.app_key == os.environ["CHERRYPULSE_PAPER_APP_KEY"]
    assert primary.app_secret == os.environ["CHERRYPULSE_PAPER_APP_SECRET"]


def test_cache_single_flight_across_threads_and_kst_expiry() -> None:
    calls: list[PaperCredentials] = []

    def issue(credentials: PaperCredentials) -> dict[str, object]:
        calls.append(credentials)
        return token_payload()

    cache = PaperTokenCache(KEYS, issue, now=lambda: START)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: cache.get(), range(20)))
    assert results == ["private-token"] * 20
    assert len(calls) == 1
    assert "private-token" not in repr(cache)
    assert parse_token(token_payload(), START)[1].astimezone(timezone.utc).hour == 1


def test_renew_before_expiry_without_retrying_failed_issue() -> None:
    clock = [START]
    calls: list[int] = []

    def issue(_credentials: PaperCredentials) -> dict[str, object]:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("secret-value private-token")  # noqa: TRY003 -- Secrecy fixture
        return token_payload()

    cache = PaperTokenCache(KEYS, issue, now=lambda: clock[0])
    assert cache.get() == "private-token"
    clock[0] = START + timedelta(minutes=59)
    with pytest.raises(PaperAuthError) as caught:
        cache.get()
    assert str(caught.value) == "AUTH_UNCONFIRMED"
    assert len(calls) == 2
    assert cache._token is None  # noqa: SLF001 -- Failed renewal must clear the cache.


def test_clock_rollback_discards_cached_token() -> None:
    clock = [START]
    cache = PaperTokenCache(KEYS, lambda _: token_payload(), now=lambda: clock[0])
    assert cache.get() == "private-token"
    clock[0] -= timedelta(seconds=1)
    with pytest.raises(PaperAuthError, match="AUTH_CLOCK_UNCERTAIN"):
        cache.get()


@pytest.mark.parametrize(
    "patch",
    [
        {"return_code": None},
        {"return_code": False},
        {"return_code": 3},
        {"token_type": None},
        {"token_type": "basic"},
        {"token": "x\ny"},
        {"expires_dt": "bad"},
        {"expires_dt": "20261014090000"},
        {"expires_dt": "20261314090000"},
    ],
)
def test_invalid_issuance_fails_closed(patch: dict[str, object]) -> None:
    cache = PaperTokenCache(KEYS, lambda _: token_payload(**patch), now=lambda: START)
    with pytest.raises(PaperAuthError, match="AUTH_UNCONFIRMED"):
        cache.get()


def test_pacer_reserves_failed_request_slots_without_wall_clock() -> None:
    clock = [0.0]
    waits: list[float] = []

    def wait(seconds: float) -> None:
        waits.append(seconds)
        clock[0] += seconds

    pacer = RequestPacer(clock=lambda: clock[0], wait=wait)
    for _ in range(3):
        pacer.acquire()
    assert waits == pytest.approx([1.1, 1.1])


@pytest.mark.parametrize("interval", [0, 0.5, float("nan"), float("inf")])
def test_unsafe_pacer_interval_rejected(interval: float) -> None:
    with pytest.raises(ValueError, match="INTERVAL_INVALID"):
        RequestPacer(interval=interval)


def test_issuer_uses_mock_and_rejects_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Request] = []

    class Opener:
        def open(self, request: Request, *, timeout: float) -> BytesIO:
            calls.append(request)
            assert timeout == 10
            return BytesIO(b'{"return_code":0,"token":"synthetic"}')

    def build(handler: HTTPRedirectHandler) -> Opener:
        assert (
            handler.redirect_request(None, None, 302, "", {}, "https://evil.example")
            is None
        )
        return Opener()

    monkeypatch.setattr("adapters.kiwoom_rest_auth.build_opener", build)
    payload = PaperTokenIssuer(RequestPacer()).issue(KEYS)
    assert payload["token"] == "synthetic"  # noqa: S105 -- Synthetic token
    assert len(calls) == 1
    assert calls[0].full_url == "https://mockapi.kiwoom.com/oauth2/token"


def test_issuer_timeout_is_sanitized_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    class Opener:
        def open(self, *_args: object, **_kwargs: object) -> None:
            calls.append(1)
            raise TimeoutError("secret-key secret-value")  # noqa: TRY003 -- Secrecy fixture

    monkeypatch.setattr("adapters.kiwoom_rest_auth.build_opener", lambda *_: Opener())
    with pytest.raises(PaperAuthError, match="AUTH_UNCONFIRMED") as caught:
        PaperTokenIssuer(RequestPacer()).issue(KEYS)
    assert "secret-key" not in str(caught.value)
    assert len(calls) == 1
