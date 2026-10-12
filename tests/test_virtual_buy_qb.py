"""Virtual Q12 first-version buy scenarios; no brokerage calls."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from contracts.buy_evaluation import evaluate_virtual_buy
from contracts.stop_evaluation import ObserveAt, Quote
from execution.facts import Cancelled, Fill
from execution.ledger import Ledger
from execution.models import Cancel, New, Request, VirtualStopBinding
from execution.outcomes import effect_confirmed, request_state
from execution.ownership import AccountLease
from execution.virtual import VirtualDispatcher

SESSION_END = datetime(2026, 10, 11, 6, 20, tzinfo=timezone.utc)
SESSION_EXPIRY = datetime(2026, 10, 11, 6, 20, tzinfo=timezone.utc)


def _qb_book(tmp_path: Path, lease: AccountLease, name: str) -> Ledger:
    """Open a virtual ledger bound to the Q12 rule-B revision."""
    book = Ledger(tmp_path / name, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930",
            version=2,
            rule_kind="AVERAGE_COST_DROP",
            threshold="0.03",
        ),
        expected_version=1,
    )
    return book


def _qb_timing() -> tuple[ObserveAt, datetime]:
    """Pin one virtual evaluation instant inside the allowed session."""
    now = datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc)
    return ObserveAt(now=now, max_quote_age_seconds=2), now


def _qb_buy(book: Ledger) -> Request:
    """Submit the single fixed-share Q12 buy intention."""
    return book.submit(
        New(
            key="qb-buy:005930:1",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=1,
            order_type="LIMIT",
            price="70000",
            session="REGULAR",
            validity="DAY",
        )
    ).request


def test_qb1_buy_fill_assigns_protection_and_blocks_same_day_rebuy(
    tmp_path: Path, lease: AccountLease
) -> None:
    book = _qb_book(tmp_path, lease, "qb1.sqlite3")
    dispatcher = VirtualDispatcher(book)
    timing, now = _qb_timing()
    decision = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=Quote(symbol="005930", price="69000", received_at=now),
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (decision.status, decision.reason, decision.qty) == (
        "BUY_CANDIDATE",
        "TARGET_AND_FRESHNESS_OK",
        1,
    )

    buy = _qb_buy(book)
    assert dispatcher.send(buy.request_id)
    dispatcher.acknowledge(buy)
    assert request_state(book.snapshot(), buy) == "ACKED"
    opened = book.order(buy.order_id)
    assert (
        opened.original,
        opened.delta,
        opened.filled,
        opened.cancelled,
        opened.active,
    ) == (
        1,
        0,
        0,
        0,
        1,
    )

    fill = Fill(
        event_id=uuid4(),
        order_id=buy.order_id,
        qty=1,
        remaining=0,
        price="70000",
        evidence_version=1,
    )
    assert book.ingest(fill)
    assert [
        (a.fill_event_id, a.qty, a.rule_version)
        for a in book.snapshot().stop_assignments
    ] == [(fill.event_id, 1, 2)]
    assert book.portfolio("005930").managed == 1
    assert book.buy_order_average_cost(buy.order_id) == Decimal(70000)
    basis = book.confirmed_stop_cost_basis("005930")
    assert basis is not None
    assert (basis.qty, basis.average_cost, basis.rule_version) == (
        1,
        Decimal(70000),
        2,
    )

    replayed = book.submit(
        New(
            key="qb-buy:005930:1",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=1,
            order_type="LIMIT",
            price="70000",
            session="REGULAR",
            validity="DAY",
        )
    )
    assert not replayed.created
    assert replayed.request.request_id == buy.request_id
    assert not dispatcher.send(buy.request_id)
    assert len(dispatcher.calls) == 1
    assert len(book.snapshot().stop_assignments) == 1

    filled_today = sum(
        f.qty
        for f in book.snapshot().facts
        if isinstance(f, Fill) and f.order_id == buy.order_id
    )
    assert filled_today == 1
    blocked = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=Quote(symbol="005930", price="68000", received_at=now),
        timing=timing,
        managed_qty=book.portfolio("005930").managed,
        filled_today_qty=filled_today,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (blocked.status, blocked.reason, blocked.qty) == (
        "BUY_BLOCKED",
        "HOLDING_BLOCKS_BUY",
        0,
    )
    assert len(book.snapshot().requests) == 1
    assert len(dispatcher.calls) == 1

    assert not book.ingest(fill)
    final = book.order(buy.order_id)
    assert (
        final.original,
        final.delta,
        final.filled,
        final.cancelled,
        final.active,
    ) == (
        1,
        0,
        1,
        0,
        0,
    )


def test_qb2_unfilled_buy_cancels_without_reorder(
    tmp_path: Path, lease: AccountLease
) -> None:
    book = _qb_book(tmp_path, lease, "qb2.sqlite3")
    dispatcher = VirtualDispatcher(book)
    timing, now = _qb_timing()
    decision = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=Quote(symbol="005930", price="69000", received_at=now),
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert decision.status == "BUY_CANDIDATE"

    buy = _qb_buy(book)
    assert dispatcher.send(buy.request_id)
    dispatcher.acknowledge(buy)
    cancel = book.submit(
        Cancel(
            key="qb2-cancel:005930:1",
            symbol="005930",
            side="BUY",
            config_version=2,
            target=buy.order_id,
            link_version=book.order(buy.order_id).link_version,
            cancel_qty=1,
        )
    ).request
    assert dispatcher.send(cancel.request_id)
    cancelled = Cancelled(
        event_id=uuid4(),
        request_id=cancel.request_id,
        order_id=buy.order_id,
        qty=1,
        remaining=0,
        evidence_version=1,
    )
    assert book.ingest(cancelled)
    assert effect_confirmed(book.snapshot(), cancel)
    final = book.order(buy.order_id)
    assert (
        final.original,
        final.delta,
        final.filled,
        final.cancelled,
        final.active,
    ) == (
        1,
        0,
        0,
        1,
        0,
    )
    assert book.portfolio("005930").managed == 0

    assert dispatcher.recover() == ()
    assert len(dispatcher.calls) == 2
    assert not dispatcher.send(buy.request_id)
    assert not dispatcher.send(cancel.request_id)
    assert len(book.snapshot().requests) == 2
    assert not book.ingest(cancelled)


def test_buy_evaluator_blocks_without_holdings_or_stale_evidence() -> None:
    timing, now = _qb_timing()
    fresh = Quote(symbol="005930", price="69000", received_at=now)

    above = evaluate_virtual_buy(
        symbol="005930",
        target_price="68000",
        quote=fresh,
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (above.status, above.reason) == ("BUY_BLOCKED", "PRICE_ABOVE_TARGET")

    equal = evaluate_virtual_buy(
        symbol="005930",
        target_price="69000",
        quote=fresh,
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (equal.status, equal.qty) == ("BUY_CANDIDATE", 1)

    edge = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=Quote(
            symbol="005930", price="69000", received_at=now - timedelta(seconds=2)
        ),
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert edge.status == "BUY_CANDIDATE"

    stale = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=Quote(
            symbol="005930", price="69000", received_at=now - timedelta(seconds=3)
        ),
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (stale.status, stale.reason) == ("BUY_BLOCKED", "QUOTE_NOT_FRESH")

    future = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=Quote(
            symbol="005930", price="69000", received_at=now + timedelta(seconds=1)
        ),
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (future.status, future.reason) == ("BUY_BLOCKED", "QUOTE_NOT_FRESH")

    missing = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=None,
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (missing.status, missing.reason) == (
        "BUY_BLOCKED",
        "QUOTE_MISSING_OR_WRONG_SYMBOL",
    )

    wrong_symbol = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=Quote(symbol="000660", price="69000", received_at=now),
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (wrong_symbol.status, wrong_symbol.reason) == (
        "BUY_BLOCKED",
        "QUOTE_MISSING_OR_WRONG_SYMBOL",
    )

    over_budget = evaluate_virtual_buy(
        symbol="005930",
        target_price="100001",
        quote=fresh,
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (over_budget.status, over_budget.reason) == (
        "BUY_BLOCKED",
        "TARGET_OVER_BUDGET",
    )

    at_budget = evaluate_virtual_buy(
        symbol="005930",
        target_price="100000",
        quote=Quote(symbol="005930", price="99999", received_at=now),
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert at_budget.status == "BUY_CANDIDATE"

    for bad_target in ("abc", "0", "-5"):
        invalid = evaluate_virtual_buy(
            symbol="005930",
            target_price=bad_target,
            quote=fresh,
            timing=timing,
            managed_qty=0,
            filled_today_qty=0,
            expires_at=SESSION_EXPIRY,
            session_end=SESSION_END,
        )
        assert (invalid.status, invalid.reason) == (
            "BUY_BLOCKED",
            "TARGET_PRICE_INVALID",
        )

    short_circuit = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=Quote(
            symbol="005930", price="69000", received_at=now - timedelta(seconds=30)
        ),
        timing=timing,
        managed_qty=1,
        filled_today_qty=1,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (short_circuit.status, short_circuit.reason) == (
        "BUY_BLOCKED",
        "HOLDING_BLOCKS_BUY",
    )


def test_buy_evaluator_enforces_expiry_and_day_reentry() -> None:
    timing, now = _qb_timing()
    fresh = Quote(symbol="005930", price="69000", received_at=now)

    missing_expiry = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=fresh,
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=None,
        session_end=SESSION_END,
    )
    assert (missing_expiry.status, missing_expiry.reason) == (
        "BUY_BLOCKED",
        "EXPIRY_REQUIRED",
    )

    naive_expiry = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=fresh,
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_END.replace(tzinfo=None),
        session_end=SESSION_END,
    )
    assert (naive_expiry.status, naive_expiry.reason) == (
        "BUY_BLOCKED",
        "EXPIRY_REQUIRED",
    )

    already_expired = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=fresh,
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=now - timedelta(seconds=1),
        session_end=SESSION_END,
    )
    assert (already_expired.status, already_expired.reason) == (
        "BUY_BLOCKED",
        "COMMAND_EXPIRED",
    )

    beyond_session = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=fresh,
        timing=timing,
        managed_qty=0,
        filled_today_qty=0,
        expires_at=SESSION_END + timedelta(hours=1),
        session_end=SESSION_END,
    )
    assert (beyond_session.status, beyond_session.reason) == (
        "BUY_BLOCKED",
        "EXPIRY_BEYOND_SESSION",
    )

    reentry = evaluate_virtual_buy(
        symbol="005930",
        target_price="70000",
        quote=fresh,
        timing=timing,
        managed_qty=0,
        filled_today_qty=1,
        expires_at=SESSION_EXPIRY,
        session_end=SESSION_END,
    )
    assert (reentry.status, reentry.reason) == ("BUY_BLOCKED", "DAY_REENTRY_BLOCKED")
