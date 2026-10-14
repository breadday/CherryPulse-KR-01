"""Explicit opt-in paper-only one-share limit buy; never touches live trading.

Default prints a preview without reading keys or network. Submission needs
``--confirm-execute`` plus ``CHERRYPULSE_PAPER_APP_KEY/SECRET`` in the current
process only. One dated sentinel under ``results/`` blocks a second submit,
including after an UNKNOWN transport outcome. Reports never contain tokens,
account numbers, or broker order numbers.
"""

# ruff: noqa: INP001 -- Standalone tool with python -m invocation.

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.request import HTTPRedirectHandler, Request, build_opener

from typing_extensions import override

from adapters.kiwoom_rest_auth import (
    MAX_RESPONSE_BYTES,
    PaperCredentials,
    PaperTokenCache,
    PaperTokenIssuer,
    RequestPacer,
)
from adapters.kiwoom_rest_order import (
    BUY_API_ID,
    DEMO_QUANTITY,
    MOCK_ORDER_URL,
    BuyPreview,
    build_buy_body,
    classify_order_response,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.client import HTTPResponse

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))


def sentinel_path(root: Path, day: str) -> Path:
    """Locate the dated single-submit guard inside the ignored results dir."""
    return root / "results" / f"paper-buy-{day}.json"


def submit_buy_body(
    body: dict[str, str],
    token: str,
    pacer: RequestPacer,
    timeout: float,
    opener_factory: Callable[[], object],
) -> dict[str, object]:
    """POST exactly once to the mock order endpoint; no redirects or retries."""
    if not math.isfinite(timeout) or not 0 < timeout <= 30:  # noqa: PLR2004 -- Upper bound for a single demo call.
        raise ValueError("TIMEOUT_INVALID")
    if not isinstance(token, str) or not token or any(c in token for c in "\r\n"):
        raise ValueError("TOKEN_INVALID")
    request = Request(  # noqa: S310 -- Fixed mock HTTPS order URL; live hosts cannot be expressed.
        MOCK_ORDER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "api-id": BUY_API_ID,
            "authorization": "Bearer " + token,
            "cont-yn": "N",
            "next-key": "",
        },
        method="POST",
    )

    pacer.acquire()
    opener = opener_factory()
    with cast(
        "HTTPResponse",
        opener.open(request, timeout=timeout),  # type: ignore[union-attr] -- Injected opener follows the urllib shape.
    ) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("RESPONSE_TOO_LARGE")
        payload = cast("object", json.loads(raw))
        if not isinstance(payload, dict):
            raise TypeError("RESPONSE_INVALID")
        return cast("dict[str, object]", payload)


def real_opener() -> object:
    """Build a private opener that refuses to follow redirects."""

    class NoRedirect(HTTPRedirectHandler):
        @override
        def redirect_request(self, *_args: object, **_kwargs: object) -> None:
            """Never forward bearer credentials to a redirect destination."""

    return build_opener(NoRedirect())


def report(
    *,
    submitted: bool,
    acked: bool,
    reason: str,
    preview: BuyPreview | None,
    network: bool,
) -> dict[str, object]:
    """Assemble a chat-safe report without secrets or broker identifiers."""
    return {
        "mode": "PAPER",
        "network": network,
        "order_submitted": submitted,
        "acked": acked,
        "reason": reason,
        "symbol": preview.symbol if preview else None,
        "qty": DEMO_QUANTITY if preview else None,
        "trade_type": "LIMIT" if preview else None,
        "price": preview.price if preview else None,
    }


def main(argv: list[str] | None = None) -> int:
    """Preview by default; submit only with explicit confirmation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="005930")
    parser.add_argument("--price", required=True)
    parser.add_argument("--confirm-execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        preview = BuyPreview(args.symbol, args.price)
    except ValueError as exc:
        _ = sys.stdout.write(
            json.dumps(
                report(
                    submitted=False,
                    acked=False,
                    reason=str(exc),
                    preview=None,
                    network=False,
                )
            )
            + "\n"
        )
        return 1
    if not args.confirm_execute:
        _ = sys.stdout.write(
            json.dumps(
                report(
                    submitted=False,
                    acked=False,
                    reason="EXECUTION_NOT_REQUESTED",
                    preview=preview,
                    network=False,
                )
            )
            + "\n"
        )
        return 0
    try:
        credentials = PaperCredentials(
            os.environ.get("CHERRYPULSE_PAPER_APP_KEY", ""),
            os.environ.get("CHERRYPULSE_PAPER_APP_SECRET", ""),
        )
        day = datetime.now(KST).strftime("%Y%m%d")
        guard = sentinel_path(ROOT, day)
        if guard.exists():
            _ = sys.stdout.write(
                json.dumps(
                    report(
                        submitted=False,
                        acked=False,
                        reason="SECOND_ORDER_BLOCKED",
                        preview=preview,
                        network=False,
                    )
                )
                + "\n"
            )
            return 1
        pacer = RequestPacer()
        issuer = PaperTokenIssuer(pacer)
        cache = PaperTokenCache(credentials, issuer.issue)
        token = cache.get()
        try:
            payload = submit_buy_body(
                build_buy_body(preview), token, pacer, 10, real_opener
            )
        except Exception:  # noqa: BLE001 -- UNKNOWN blocks resubmission; context never echoed.
            guard.parent.mkdir(exist_ok=True)
            _ = guard.write_text(
                json.dumps({"date": day, "status": "UNKNOWN"}), encoding="utf-8"
            )
            _ = sys.stdout.write(
                json.dumps(
                    report(
                        submitted=True,
                        acked=False,
                        reason="TRANSPORT_UNKNOWN",
                        preview=preview,
                        network=True,
                    )
                )
                + "\n"
            )
            return 1
        acked, reason = classify_order_response(payload)
        if acked:
            guard.parent.mkdir(exist_ok=True)
            _ = guard.write_text(
                json.dumps(
                    {
                        "date": day,
                        "symbol": preview.symbol,
                        "qty": DEMO_QUANTITY,
                        "price": preview.price,
                        "status": "ACKED",
                    }
                ),
                encoding="utf-8",
            )
    except Exception:  # noqa: BLE001 -- Do not echo credentials or auth exception context.
        _ = sys.stdout.write(
            json.dumps(
                report(
                    submitted=False,
                    acked=False,
                    reason="SETUP_OR_AUTH_UNCONFIRMED",
                    preview=preview,
                    network=False,
                )
            )
            + "\n"
        )
        return 1
    else:
        _ = sys.stdout.write(
            json.dumps(
                report(
                    submitted=True,
                    acked=acked,
                    reason=reason,
                    preview=preview,
                    network=True,
                )
            )
            + "\n"
        )
        return 0 if acked else 1


if __name__ == "__main__":
    raise SystemExit(main())
