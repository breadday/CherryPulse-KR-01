"""Mock-server-only REST transport; deliberately excludes order endpoints."""

# pyright: reportUnnecessaryIsInstance=false, reportUnreachable=false
# Runtime validation deliberately checks untrusted injected responses.

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, cast
from urllib.request import HTTPRedirectHandler, Request, build_opener

from typing_extensions import override

from adapters.kiwoom_rest_auth import MAX_RESPONSE_BYTES, RequestPacer
from adapters.kiwoom_rest_readonly import RestPage, RestQuery, validate_query

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.client import HTTPResponse


class PaperReadOnlyTransport:
    """Use an externally obtained token only on the fixed Kiwoom mock host."""

    def __init__(
        self,
        token_provider: Callable[[], str],
        *,
        timeout: float,
        pacer: RequestPacer | None = None,
    ) -> None:
        """Require a bounded timeout and keep credentials out of result objects."""
        if not math.isfinite(timeout) or not 0 < timeout <= 30:  # noqa: PLR2004 -- Upper bound for a read-only call.
            raise ValueError("TIMEOUT_INVALID")
        self._token_provider: Callable[[], str] = token_provider
        self._timeout: float = timeout
        self._pacer: RequestPacer = pacer if pacer is not None else RequestPacer()

    def fetch_page(
        self,
        query: RestQuery,
        body: dict[str, str],
        cont_yn: str,
        next_key: str,
    ) -> RestPage:
        """Issue exactly one read-only POST; no redirects or automatic retries."""
        if not isinstance(query, RestQuery):
            raise TypeError("QUERY_NOT_READ_ONLY")
        validate_query(query, body, 1)
        token = self._token_provider()
        if not isinstance(token, str) or not token or any(c in token for c in "\r\n"):
            raise ValueError("TOKEN_INVALID")
        request = Request(
            "https://mockapi.kiwoom.com/api/dostk/acnt",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "api-id": query.value,
                "authorization": "Bearer " + token,
                "cont-yn": cont_yn,
                "next-key": next_key,
            },
            method="POST",
        )

        # A private opener prevents forwarding credentials through redirects.
        class NoRedirect(HTTPRedirectHandler):
            @override
            def redirect_request(self, *_args: object, **_kwargs: object) -> None:
                """Never forward bearer credentials to a redirect destination."""

        self._pacer.acquire()
        with cast(
            "HTTPResponse",
            build_opener(NoRedirect()).open(request, timeout=self._timeout),
        ) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("RESPONSE_TOO_LARGE")
            payload = cast("object", json.loads(raw))
            if not isinstance(payload, dict):
                raise TypeError("RESPONSE_INVALID")
            return RestPage(
                cast("dict[str, object]", payload),
                response.headers.get("cont-yn", ""),
                response.headers.get("next-key", ""),
            )
