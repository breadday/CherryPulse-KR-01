"""Characterization locks for manual general-sell guards and precedence."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from contracts.sell_evaluation import (
    ManualSellProposal,
    propose_manual_general_sell,
)
from contracts.stop_evaluation import (
    ManagedPosition,
    ObserveAt,
    ProtectionExposure,
    Quote,
)

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 28, 13, 0, tzinfo=KST)
SESSION_START = datetime(2026, 10, 28, 9, 0, tzinfo=KST)
SESSION_END = datetime(2026, 10, 28, 15, 30, tzinfo=KST)


def _exposure(**overrides: object) -> ProtectionExposure:
    values: dict[str, object] = {
        "managed_qty": 3,
        "reserved_sell_qty": 0,
        "reconciliation_required": False,
        "sell_uncertain": False,
    }
    values.update(overrides)
    return ProtectionExposure(**values)  # type: ignore[arg-type]


def _propose(**overrides: object) -> ManualSellProposal:
    values: dict[str, object] = {
        "position": ManagedPosition(
            symbol="005930", confirmed_qty=3, average_cost="10000"
        ),
        "exposure": _exposure(),
        "quote": Quote(symbol="005930", price="10000", received_at=NOW),
        "timing": ObserveAt(now=NOW, max_quote_age_seconds=2),
        "session_start": SESSION_START,
        "session_end": SESSION_END,
        "submitted_by_user": True,
    }
    values.update(overrides)
    return propose_manual_general_sell(**values)  # type: ignore[arg-type]


def test_ready_full_and_half_even() -> None:
    full = _propose()
    assert full == ManualSellProposal(
        status="READY",
        reason="EXPLICIT_MANUAL_SELL_VALIDATED",
        qty=3,
        order_kind="LIMIT",
        limit_price=Decimal(10000),
        expires_at=SESSION_END,
    )
    half = _propose(
        position=ManagedPosition(
            symbol="005930", confirmed_qty=4, average_cost="10000"
        ),
        exposure=_exposure(managed_qty=4),
        quantity_mode="HALF",
        order_kind="MARKET",
        market_confirmed=True,
    )
    assert half.status == "READY"
    assert (half.qty, half.order_kind, half.limit_price) == (2, "MARKET", None)
    assert half.expires_at == SESSION_END


def test_explicit_submission_and_choice_gates_come_first() -> None:
    blocked = _propose(
        submitted_by_user=False,
        quantity_mode="UNSUPPORTED",
        order_kind="UNSUPPORTED",
        stop_priority_due=True,
    )
    assert blocked.reason == "MANUAL_SUBMISSION_REQUIRED"
    mode = _propose(
        quantity_mode="UNSUPPORTED",
        order_kind="UNSUPPORTED",
        stop_priority_due=True,
    )
    assert mode.reason == "QUANTITY_MODE_UNSUPPORTED"
    kind = _propose(
        order_kind="UNSUPPORTED",
        stop_priority_due=True,
        position=ManagedPosition(symbol="005930", confirmed_qty=0),
    )
    assert kind.reason == "ORDER_KIND_UNSUPPORTED"
    stop = _propose(
        stop_priority_due=True,
        position=ManagedPosition(symbol="005930", confirmed_qty=0),
    )
    assert stop.reason == "STOP_HAS_PRIORITY"


def test_position_and_ledger_evidence_gates() -> None:
    empty = _propose(position=ManagedPosition(symbol="005930", confirmed_qty=0))
    assert empty.reason == "NO_MANAGED_POSITION"
    mismatch = _propose(exposure=_exposure(managed_qty=2))
    assert mismatch.reason == "POSITION_EVIDENCE_MISMATCH"
    over = _propose(exposure=_exposure(reserved_sell_qty=4))
    assert over.reason == "SELL_RESERVATION_EXCEEDS_HOLDING"
    unresolved = _propose(
        exposure=_exposure(reconciliation_required=True, sell_uncertain=True)
    )
    assert unresolved.reason == "SELL_EVIDENCE_UNRESOLVED"
    reserved = _propose(exposure=_exposure(reserved_sell_qty=1))
    assert reserved.reason == "SELL_ALREADY_RESERVED"


def test_naive_session_clock_is_rejected_before_window_rules() -> None:
    blocked = _propose(
        session_start=datetime(2026, 10, 28, 9, 0),  # noqa: DTZ001 -- deliberately naive to exercise the tz gate.
        session_end=datetime(2026, 10, 28, 15, 30),  # noqa: DTZ001 -- deliberately naive to exercise the tz gate.
    )
    assert blocked.reason == "SESSION_TIMEZONE_REQUIRED"


def test_session_window_gates_and_precedence() -> None:
    prev_day = _propose(
        session_start=datetime(2026, 10, 27, 9, 0, tzinfo=KST),
        session_end=datetime(2026, 10, 27, 15, 30, tzinfo=KST),
    )
    assert prev_day.reason == "SAME_DAY_SESSION_REQUIRED"
    off_day = _propose(
        session_start=datetime(2026, 10, 29, 3, 0, tzinfo=UTC),
        session_end=datetime(2026, 10, 29, 6, 30, tzinfo=UTC),
    )
    assert off_day.reason == "SAME_DAY_SESSION_REQUIRED"
    reversed_range = _propose(
        session_start=datetime(2026, 10, 28, 15, 0, tzinfo=KST),
        session_end=datetime(2026, 10, 28, 15, 0, tzinfo=KST),
    )
    assert reversed_range.reason == "INVALID_SESSION_RANGE"
    early = _propose(
        timing=ObserveAt(
            now=datetime(2026, 10, 28, 8, 0, tzinfo=KST), max_quote_age_seconds=2
        )
    )
    assert early.reason == "SESSION_NOT_STARTED"
    expired = _propose(
        timing=ObserveAt(
            now=datetime(2026, 10, 28, 15, 30, tzinfo=KST), max_quote_age_seconds=2
        )
    )
    assert expired.reason == "SESSION_EXPIRED"


def test_market_confirmation_gate() -> None:
    blocked = _propose(order_kind="MARKET", market_confirmed=False)
    assert blocked.reason == "MARKET_CONFIRMATION_REQUIRED"


def test_quote_gates_precede_quantity_check() -> None:
    """Quote gates must win over the later whole-quantity HALF gate."""
    missing = _propose(quote=None)
    assert missing.reason == "QUOTE_MISSING_OR_WRONG_SYMBOL"
    wrong_symbol = _propose(
        quote=Quote(symbol="000660", price="10000", received_at=NOW)
    )
    assert wrong_symbol.reason == "QUOTE_MISSING_OR_WRONG_SYMBOL"
    stale = _propose(
        quote=Quote(
            symbol="005930", price="10000", received_at=NOW - timedelta(seconds=3)
        )
    )
    assert stale.reason == "QUOTE_NOT_FRESH"
    future = _propose(
        quote=Quote(
            symbol="005930", price="10000", received_at=NOW + timedelta(seconds=1)
        )
    )
    assert future.reason == "QUOTE_NOT_FRESH"
    half_odd_bad_quote = _propose(quantity_mode="HALF", quote=None)
    assert half_odd_bad_quote.reason == "QUOTE_MISSING_OR_WRONG_SYMBOL"


def test_half_quantity_gate() -> None:
    blocked = _propose(quantity_mode="HALF")
    assert blocked.reason == "HALF_QTY_NOT_WHOLE"
