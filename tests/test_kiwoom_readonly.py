from dataclasses import replace
from datetime import datetime, timezone

import pytest

from adapters.kiwoom_readonly import (
    POSITIONS_FIELDS,
    QueryPage,
    QuerySpec,
    QueryStatus,
    ReadOnlyQueryError,
    new_capture,
    normalize_capture,
    pagination_complete,
)

NOW = datetime(2026, 9, 25, 1, 0, tzinfo=timezone.utc)


def positions_spec() -> QuerySpec:
    return QuerySpec(
        tr_code="opw00018",
        rq_name="readonly_positions",
        input_values={"계좌번호": "ACCOUNT_ALIAS_ONLY"},
        fields=POSITIONS_FIELDS,
    )


def test_complete_pages_are_normalized_for_display_only() -> None:
    capture = new_capture(
        positions_spec(), account_alias="acct-a", environment="PAPER", started_at=NOW
    )
    capture = replace(
        capture,
        finished_at=NOW,
        pages=(
            QueryPage(
                1,
                "0",
                NOW,
                ({"종목번호": " A005930 ", "보유수량": " 10 "},),
                raw_payload="redacted-local-payload",
                finished=True,
            ),
        ),
    )
    snapshot = normalize_capture(capture)
    assert snapshot.status is QueryStatus.COMPLETE
    assert snapshot.rows[0]["종목번호"] == "A005930"
    assert snapshot.reason == "READ_ONLY_QUERY_COMPLETE_NOT_MANAGED"
    assert capture.spec.input_values["계좌번호"] == "<redacted>"


@pytest.mark.parametrize(
    ("pages", "finished", "expected"),
    [
        ((), None, QueryStatus.UNKNOWN),
        ((QueryPage(2, "0", NOW, finished=True),), NOW, QueryStatus.QUARANTINED),
        ((QueryPage(1, "2", NOW, finished=True),), NOW, QueryStatus.QUARANTINED),
        ((QueryPage(1, "0", NOW, error_code="TIMEOUT"),), NOW, QueryStatus.QUARANTINED),
    ],
)
def test_incomplete_or_missing_pages_are_quarantined(
    pages: tuple[QueryPage, ...], finished: datetime | None, expected: QueryStatus
) -> None:
    capture = new_capture(
        positions_spec(), account_alias="acct-a", environment="PAPER", started_at=NOW
    )
    capture = replace(capture, finished_at=finished, pages=pages)
    assert capture.status is expected
    assert normalize_capture(capture).rows == ()


def test_unverified_fill_history_tr_is_blocked() -> None:
    with pytest.raises(ReadOnlyQueryError, match="TR_NOT_READ_ONLY"):
        _ = QuerySpec(
            tr_code="opw00007",
            rq_name="readonly_fills",
            input_values={"계좌번호": "ACCOUNT_ALIAS_ONLY"},
            fields=(),
        )


def test_non_whitelisted_tr_cannot_be_requested() -> None:
    with pytest.raises(ReadOnlyQueryError, match="TR_NOT_READ_ONLY"):
        _ = QuerySpec("SendOrder", "unsafe", {}, ())


@pytest.mark.parametrize(
    ("markers", "expected"),
    [
        ((), False),
        (("",), True),
        (("2",), False),
        (("2", "0"), True),
        (("2", "2", ""), True),
        (("0", "0"), False),
        (("2", "UNKNOWN"), False),
    ],
)
def test_pagination_requires_terminal_after_continuations(
    markers: tuple[str, ...], *, expected: bool
) -> None:
    assert pagination_complete(markers) is expected


def test_duplicate_terminal_page_is_quarantined() -> None:
    capture = new_capture(
        positions_spec(), account_alias="acct-a", environment="PAPER", started_at=NOW
    )
    capture = replace(
        capture,
        finished_at=NOW,
        pages=(
            QueryPage(1, "0", NOW, finished=True),
            QueryPage(2, "0", NOW, finished=True),
        ),
    )
    assert capture.status is QueryStatus.QUARANTINED
