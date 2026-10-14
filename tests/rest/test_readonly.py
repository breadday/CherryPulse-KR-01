"""Offline REST contract tests, runnable independently of Windows ledger tests."""

from io import BytesIO
from typing import ClassVar
from urllib.request import HTTPRedirectHandler, Request

import pytest

from adapters.kiwoom_rest_readonly import (
    RestCapture,
    RestPage,
    RestQuery,
    capture_query,
)
from adapters.kiwoom_rest_transport import PaperReadOnlyTransport

BODY = {"qry_tp": "2", "dmst_stex_tp": "KRX"}


class FakeTransport:
    def __init__(self, *pages: RestPage | Exception | None) -> None:
        self.pages = iter(pages)
        self.calls: list[tuple[RestQuery, dict[str, str], str, str]] = []

    def fetch_page(
        self, query: RestQuery, body: dict[str, str], cont_yn: str, next_key: str
    ) -> RestPage:
        """Return synthetic pages including intentionally invalid responses."""
        self.calls.append((query, body, cont_yn, next_key))
        page = next(self.pages)
        if isinstance(page, Exception):
            raise page
        return page  # type: ignore[return-value] -- malformed transport injection


def page(marker: str = "N", cursor: str = "", **patch: object) -> RestPage:
    payload: dict[str, object] = {"return_code": 0, "acnt_evlt_remn_indv_tot": []}
    payload.update(patch)
    return RestPage(payload, marker, cursor)


def capture(transport: FakeTransport, limit: int = 3) -> RestCapture:
    return capture_query(transport, RestQuery.POSITIONS, BODY, max_pages=limit)


def test_complete_empty_is_explicit() -> None:
    result = capture(FakeTransport(page()))
    assert result.complete
    assert result.reason == "QUERY_COMPLETE_ONLY"


def test_cursor_forwarding_and_input_copy() -> None:
    transport = FakeTransport(page("Y", "cursor-1"), page())
    result = capture(transport)
    assert result.complete
    assert transport.calls[1][2:] == ("Y", "cursor-1")
    assert transport.calls[0][1] is not BODY


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (page(return_code=3), "API_SUCCESS_UNCONFIRMED"),
        (page(return_code=None), "API_SUCCESS_UNCONFIRMED"),
        (page(return_code=False), "API_SUCCESS_UNCONFIRMED"),
        (page(acnt_evlt_remn_indv_tot=None), "ROWS_INVALID"),
        (page(acnt_evlt_remn_indv_tot=["bad"]), "ROWS_INVALID"),
        (page(""), "CONTINUATION_UNCONFIRMED"),
        (page("Y"), "CURSOR_MISSING"),
        (None, "RESPONSE_INVALID"),
        (RestPage({}, "N", None), "RESPONSE_INVALID"),  # type: ignore[arg-type]
        (RestPage(None, "N", ""), "RESPONSE_INVALID"),  # type: ignore[arg-type]
    ],
)
def test_ambiguous_response_is_not_empty_success(
    response: RestPage | None, reason: str
) -> None:
    transport = FakeTransport(response)
    result = capture(transport)
    assert not result.complete
    assert result.reason == reason
    assert len(transport.calls) == 1


def test_timeout_preserves_partial_pages_without_retry_or_secret() -> None:
    transport = FakeTransport(page("Y", "cursor"), TimeoutError("SECRET_TOKEN"))
    result = capture(transport)
    assert not result.complete
    assert len(result.pages) == 1
    assert len(transport.calls) == 2
    assert "SECRET_TOKEN" not in repr(result)


def test_page_limit_is_not_complete() -> None:
    result = capture(FakeTransport(page("Y", "cursor")), limit=1)
    assert not result.complete
    assert result.reason == "PAGE_LIMIT_REACHED"


def test_cursor_cycle_stops() -> None:
    transport = FakeTransport(page("Y", "a"), page("Y", "b"), page("Y", "a"))
    result = capture(transport)
    assert not result.complete
    assert result.reason == "CURSOR_REPEATED"


@pytest.mark.parametrize("query", ["kt10000", "kt00018", None])
def test_arbitrary_or_order_api_never_reaches_transport(query: object) -> None:
    transport = FakeTransport()
    with pytest.raises(TypeError, match="QUERY_NOT_READ_ONLY"):
        capture_query(transport, query, BODY, max_pages=1)  # type: ignore[arg-type]
    assert transport.calls == []


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limits_never_reach_transport(limit: object) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError, match="PAGE_LIMIT_INVALID"):
        capture(transport, limit)  # type: ignore[arg-type]
    assert transport.calls == []


@pytest.mark.parametrize(
    "body", [{}, {**BODY, "token": "secret"}, {**BODY, "qry_tp": 2}]
)
def test_extra_or_missing_input_never_reaches_transport(body: dict[str, str]) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError, match="QUERY_INPUT_INVALID"):
        capture_query(transport, RestQuery.POSITIONS, body, max_pages=1)
    assert transport.calls == []


def test_unfilled_uses_own_row_key() -> None:
    transport = FakeTransport(RestPage({"return_code": "0", "oso": []}, "N", ""))
    result = capture_query(
        transport,
        RestQuery.UNFILLED,
        {"all_stk_tp": "0", "trde_tp": "0", "stex_tp": "0"},
        max_pages=1,
    )
    assert result.complete


def test_mock_transport_uses_fixed_host_and_one_read_only_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    calls: list[Request] = []

    class Response(BytesIO):
        headers: ClassVar[dict[str, str]] = {"cont-yn": "N", "next-key": ""}

    class Opener:
        def open(self, request: Request, *, timeout: float) -> Response:
            calls.append(request)
            assert timeout == 5
            return Response(b'{"return_code":0,"acnt_evlt_remn_indv_tot":[]}')

    monkeypatch.setattr(
        "adapters.kiwoom_rest_transport.build_opener", lambda *_: Opener()
    )
    result = capture(PaperReadOnlyTransport(lambda: "secret", timeout=5))  # type: ignore[arg-type]
    assert result.complete
    assert len(calls) == 1
    assert calls[0].full_url == "https://mockapi.kiwoom.com/api/dostk/acnt"
    assert calls[0].get_header("Api-id") == "kt00018"
    assert "secret" not in repr(result)


def test_mock_transport_refuses_redirects(monkeypatch: pytest.MonkeyPatch) -> None:

    class Opener:
        def open(self, *_args: object, **_kwargs: object) -> None:
            raise TimeoutError("secret")

    def build(handler: HTTPRedirectHandler) -> Opener:
        assert (
            handler.redirect_request(None, None, 302, "", {}, "https://evil.example")
            is None
        )
        return Opener()

    monkeypatch.setattr("adapters.kiwoom_rest_transport.build_opener", build)
    result = capture(PaperReadOnlyTransport(lambda: "secret", timeout=5))  # type: ignore[arg-type]
    assert not result.complete
    assert result.reason == "TRANSPORT_UNCONFIRMED"
