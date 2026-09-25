"""Durable, inert stop rule binding in the virtual ledger."""

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.stop_evaluation import ObserveAt, Quote
from execution.facts import Cancelled, Fill, Rejected, SendFailed, Transport
from execution.ledger import Ledger
from execution.models import Allocation, Cancel, LedgerError, New, VirtualStopBinding
from execution.ownership import AccountLease
from execution.stop_obligations import stop_obligation_views
from execution.virtual import VirtualDispatcher


def test_stop_rule_replays_after_restart_and_version_mismatch_is_inert(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    first = VirtualStopBinding(
        symbol="005930", version=2, rule_kind="PRICE_AT_OR_BELOW", threshold="9800"
    )
    book.apply_virtual_stop_config(first, expected_version=1)
    assert Ledger(path, lease).virtual_stop_binding("005930") == first
    assert book.snapshot().revision == 2

    with pytest.raises(LedgerError, match="STALE_CONFIG_VERSION"):
        book.apply_virtual_stop_config(first, expected_version=1)
    assert book.snapshot().revision == 2

    # A legacy numeric-only revision cannot be mistaken for a bound stop rule.
    book.apply_config("005930", expected_version=2, version=3)
    assert Ledger(path, lease).virtual_stop_binding("005930") is None
    second = VirtualStopBinding(
        symbol="005930", version=4, rule_kind="AVERAGE_COST_DROP", threshold="0.02"
    )
    book.apply_virtual_stop_config(second, expected_version=3)
    assert Ledger(path, lease).virtual_stop_binding("005930") == second


def test_stop_rule_rejects_invalid_and_approximate_thresholds() -> None:
    for threshold in ("0", "1", "2"):
        with pytest.raises((ValidationError, LedgerError)):
            _ = VirtualStopBinding(
                symbol="005930",
                version=1,
                rule_kind="AVERAGE_COST_DROP",
                threshold=threshold,
            )
    with pytest.raises(ValidationError):
        _ = VirtualStopBinding(
            symbol="005930",
            version=1,
            rule_kind="PRICE_AT_OR_BELOW",
            threshold=9800.0,  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError, match="STOP_LINK_REQUIRES_MARKET_SELL"):
        _ = New(
            key="invalid-stop-buy",
            symbol="005930",
            side="BUY",
            config_version=1,
            qty=1,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
            stop_latch_version=1,
        )


def test_buy_partial_fills_assign_order_rule_once_and_restore_after_restart(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    binding = VirtualStopBinding(
        symbol="005930", version=2, rule_kind="PRICE_AT_OR_BELOW", threshold="9800"
    )
    book.apply_virtual_stop_config(binding, expected_version=1)
    buy = book.submit(
        New(
            key="buy-for-stop",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=7,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    book.apply_config("005930", expected_version=2, version=3)
    first = Fill(
        event_id=uuid4(), order_id=buy.order_id, qty=4, remaining=3, evidence_version=1
    )
    second = Fill(
        event_id=uuid4(), order_id=buy.order_id, qty=3, remaining=0, evidence_version=2
    )
    assert book.ingest(first)
    assert not book.ingest(first)
    assert book.ingest(second)
    restored = Ledger(path, lease)
    assignments = restored.snapshot().stop_assignments
    assert [(a.fill_event_id, a.qty, a.rule_version) for a in assignments] == [
        (first.event_id, 4, 2),
        (second.event_id, 3, 2),
    ]
    assert restored.portfolio("005930").managed == 7
    assert restored.virtual_stop_binding("005930") is None
    assert restored.buy_order_average_cost(buy.order_id) is None
    assert restored.confirmed_stop_cost_basis("005930") is None
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    decision = restored.virtual_price_stop_candidate(
        "005930",
        Quote(symbol="005930", price="9700", received_at=now),
        ObserveAt(now=now, max_quote_age_seconds=2),
    )
    assert (decision.status, decision.unreserved_qty) == ("CANDIDATE", 7)


def test_fixed_price_stop_accounts_for_partial_sell_without_cost(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930",
            version=2,
            rule_kind="PRICE_AT_OR_BELOW",
            threshold="9800",
        ),
        expected_version=1,
    )
    buy = book.submit(
        New(
            key="unpriced-buy",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=7,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=4,
            remaining=3,
            evidence_version=1,
        )
    )
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    quote = Quote(symbol="005930", price="9700", received_at=now)
    timing = ObserveAt(now=now, max_quote_age_seconds=2)
    assert (
        book.virtual_price_stop_candidate("005930", quote, timing).unreserved_qty == 4
    )
    stale = Quote(symbol="005930", price="9700", received_at=now - timedelta(seconds=3))
    assert book.virtual_price_stop_candidate("005930", stale, timing).status == "NONE"
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=3,
            remaining=0,
            evidence_version=2,
        )
    )
    sell = book.submit(
        New(
            key="existing-sell",
            symbol="005930",
            side="SELL",
            config_version=2,
            qty=2,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert (
        book.virtual_price_stop_candidate("005930", quote, timing).unreserved_qty == 5
    )
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=sell.order_id,
            qty=2,
            remaining=0,
            evidence_version=1,
        )
    )
    restored = Ledger(path, lease)
    assert (
        restored.virtual_price_stop_candidate("005930", quote, timing).unreserved_qty
        == 5
    )
    assert (
        restored.virtual_cost_stop_candidate("005930", quote, timing).status
        == "BLOCKED"
    )
    assert book.ingest(
        Transport(event_id=uuid4(), request_id=sell.request_id, state="UNKNOWN")
    )
    uncertain = Ledger(path, lease).virtual_price_stop_candidate(
        "005930", quote, timing
    )
    assert (uncertain.status, uncertain.reason) == (
        "BLOCKED",
        "SELL_EVIDENCE_UNRESOLVED",
    )


def test_fixed_stop_latch_survives_restart_and_protects_late_buy_fill(  # noqa: PLR0915
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930",
            version=2,
            rule_kind="PRICE_AT_OR_BELOW",
            threshold="9800",
        ),
        expected_version=1,
    )
    buy = book.submit(
        New(
            key="partially-filled",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=7,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    pending = book.submit(
        New(
            key="pending-other-buy",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=1,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=4,
            remaining=3,
            evidence_version=1,
        )
    )
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    timing = ObserveAt(now=now, max_quote_age_seconds=2)
    quote = Quote(symbol="005930", price="9700", received_at=now)
    quote_result = book.process_virtual_stop_quote("005930", quote, timing)
    assert quote_result.accepted
    assert quote_result.observation.status == "TRIGGERED"
    latch = quote_result.latch
    assert latch is not None
    assert book.latch_virtual_price_stop("005930", quote, timing) == latch
    assert len(book.snapshot().stop_latches) == 1
    before_requests = len(book.snapshot().requests)
    with pytest.raises(LedgerError, match="STOP_LATCH_LINK_NOT_FOUND"):
        _ = book.submit(
            New(
                key="virtual-stop:005930:wrong-link",
                symbol="005930",
                side="SELL",
                config_version=2,
                qty=1,
                order_type="MARKET",
                session="REGULAR",
                validity="DAY",
                stop_latch_version=3,
            )
        )
    assert len(book.snapshot().requests) == before_requests
    with pytest.raises(LedgerError, match="STOP_LATCH_LINK_REQUIRED"):
        _ = book.submit(
            New(
                key="virtual-stop:005930:unlinked",
                symbol="005930",
                side="SELL",
                config_version=2,
                qty=1,
                order_type="MARKET",
                session="REGULAR",
                validity="DAY",
            )
        )
    assert len(book.snapshot().requests) == before_requests
    assert book.virtual_latched_stop_candidate("005930").unreserved_qty == 4
    dispatcher = VirtualDispatcher(book)
    assert not dispatcher.real_order_transport_available
    assert not dispatcher.send(pending.request_id)
    assert dispatcher.drain_virtual_stop("005930", session="CLOSED") is None
    first_sell = dispatcher.drain_virtual_stop("005930", session="REGULAR")
    assert first_sell is not None
    assert isinstance(first_sell.command, New)
    assert first_sell.command.qty == 4
    assert first_sell.command.stop_latch_version == latch.rule_version
    first_obligation = book.snapshot().stop_sell_obligations
    assert len(first_obligation) == 1
    assert (
        first_obligation[0].request_id,
        first_obligation[0].order_id,
        first_obligation[0].qty,
        first_obligation[0].rule_version,
    ) == (first_sell.request_id, first_sell.order_id, 4, latch.rule_version)
    assert not book.submit(first_sell.command).created
    assert book.snapshot().stop_sell_obligations == first_obligation
    assert not dispatcher.send(first_sell.request_id, stop_session="CLOSED")
    assert dispatcher.drain_virtual_stop("005930", session="REGULAR") is None
    with pytest.raises(LedgerError, match="ENTRY_STOP_LATCHED"):
        _ = book.submit(
            New(
                key="new-entry-blocked",
                symbol="005930",
                side="BUY",
                config_version=2,
                qty=1,
                order_type="MARKET",
                session="REGULAR",
                validity="DAY",
            )
        )
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=3,
            remaining=0,
            evidence_version=2,
        )
    )
    restored = Ledger(path, lease)
    assert restored.virtual_latched_stop_candidate("005930").unreserved_qty == 3
    late_sell = dispatcher.drain_virtual_stop("005930", session="REGULAR")
    assert late_sell is not None
    assert isinstance(late_sell.command, New)
    assert late_sell.command.qty == 3
    assert late_sell.command.stop_latch_version == latch.rule_version
    assert Ledger(path, lease).snapshot().requests[-1].command == late_sell.command
    assert [
        (item.request_id, item.qty)
        for item in Ledger(path, lease).snapshot().stop_sell_obligations
    ] == [(first_sell.request_id, 4), (late_sell.request_id, 3)]
    assert restored.virtual_latched_stop_candidate("005930").unreserved_qty == 0
    cancel = restored.submit(
        Cancel(
            key="unknown-stop-cancel",
            symbol="005930",
            side="SELL",
            config_version=2,
            target=late_sell.order_id,
            link_version=restored.order(late_sell.order_id).link_version,
            cancel_qty=3,
        )
    ).request
    assert restored.ingest(
        Transport(event_id=uuid4(), request_id=cancel.request_id, state="UNKNOWN")
    )
    blocked = Ledger(path, lease).virtual_latched_stop_candidate("005930")
    assert (blocked.status, blocked.reason, blocked.unreserved_qty) == (
        "BLOCKED",
        "SELL_EVIDENCE_UNRESOLVED",
        0,
    )
    assert all(
        view.state == "BLOCKED_EVIDENCE"
        for view in restored.virtual_stop_obligations("005930")
    )
    restarted_dispatcher = VirtualDispatcher(Ledger(path, lease))
    recovered = set(restarted_dispatcher.recover())
    assert {buy.request_id, cancel.request_id} <= recovered
    assert restarted_dispatcher.drain_virtual_stop("005930", session="REGULAR") is None
    assert restarted_dispatcher.calls == []


def test_cost_stop_latch_requires_price_then_preserves_residual_after_sale(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930",
            version=2,
            rule_kind="AVERAGE_COST_DROP",
            threshold="0.02",
        ),
        expected_version=1,
    )
    buy = book.submit(
        New(
            key="priced-stop-buy",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=3,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    timing = ObserveAt(now=now, max_quote_age_seconds=2)
    quote = Quote(symbol="005930", price="9700", received_at=now)
    assert book.latch_virtual_cost_stop("005930", quote, timing) is None
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=1,
            remaining=2,
            evidence_version=1,
            price="10000",
        )
    )
    latch = book.latch_virtual_cost_stop("005930", quote, timing)
    assert latch is not None
    assert book.virtual_latched_stop_candidate("005930").unreserved_qty == 1
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=2,
            remaining=0,
            evidence_version=2,
            price="10000",
        )
    )
    assert (
        Ledger(path, lease).virtual_latched_stop_candidate("005930").unreserved_qty == 3
    )
    sell = book.submit(
        New(
            key="cost-stop-sell",
            symbol="005930",
            side="SELL",
            config_version=2,
            qty=1,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=sell.order_id,
            qty=1,
            remaining=0,
            evidence_version=1,
        )
    )
    assert book.confirmed_stop_cost_basis("005930") is None
    assert (
        Ledger(path, lease).virtual_latched_stop_candidate("005930").unreserved_qty == 2
    )


def test_stop_obligation_remains_one_request_during_partial_sell(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930", version=2, rule_kind="PRICE_AT_OR_BELOW", threshold="9800"
        ),
        expected_version=1,
    )
    buy = book.submit(
        New(
            key="protected-buy",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=4,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=4,
            remaining=0,
            evidence_version=1,
        )
    )
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    assert (
        book.latch_virtual_price_stop(
            "005930",
            Quote(symbol="005930", price="9700", received_at=now),
            ObserveAt(now=now, max_quote_age_seconds=2),
        )
        is not None
    )
    dispatcher = VirtualDispatcher(book)
    sell = dispatcher.drain_virtual_stop("005930", session="REGULAR")
    assert sell is not None
    obligation = book.snapshot().stop_sell_obligations
    assert len(obligation) == 1
    assert (obligation[0].request_id, obligation[0].qty) == (sell.request_id, 4)
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=sell.order_id,
            qty=2,
            remaining=2,
            evidence_version=1,
        )
    )
    restored = Ledger(path, lease)
    assert restored.snapshot().stop_sell_obligations == obligation
    view = restored.virtual_stop_obligations("005930")
    assert len(view) == 1
    assert (view[0].initial_qty, view[0].filled_qty, view[0].unfilled_qty) == (4, 2, 2)
    assert view[0].state == "PENDING"
    assert view[0].next_action == "QUERY_BROKER"
    without_latch = replace(restored.snapshot(), stop_latches=())
    damaged_view = stop_obligation_views(without_latch, "005930")
    assert damaged_view[0].state == "BLOCKED_EVIDENCE"
    assert damaged_view[0].next_action == "QUERY_BROKER"
    duplicated = replace(
        restored.snapshot(), stop_sell_obligations=obligation + obligation
    )
    assert all(
        item.state == "BLOCKED_EVIDENCE"
        for item in stop_obligation_views(duplicated, "005930")
    )
    assert restored.virtual_latched_stop_candidate("005930").unreserved_qty == 0
    assert dispatcher.drain_virtual_stop("005930", session="REGULAR") is None
    restarted_dispatcher = VirtualDispatcher(restored)
    assert restarted_dispatcher.recover() == (buy.request_id,)
    assert restarted_dispatcher.drain_virtual_stop("005930", session="REGULAR") is None
    assert restarted_dispatcher.calls == []


def test_blocked_obligation_prevents_later_virtual_stop_sell(
    tmp_path: Path, lease: AccountLease, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = Ledger(tmp_path / "ledger.sqlite3", lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930", version=2, rule_kind="PRICE_AT_OR_BELOW", threshold="9800"
        ),
        expected_version=1,
    )
    buy = book.submit(
        New(
            key="protected-buy",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=4,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=2,
            remaining=2,
            evidence_version=1,
        )
    )
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    assert (
        book.latch_virtual_price_stop(
            "005930",
            Quote(symbol="005930", price="9700", received_at=now),
            ObserveAt(now=now, max_quote_age_seconds=2),
        )
        is not None
    )
    dispatcher = VirtualDispatcher(book)
    assert dispatcher.drain_virtual_stop("005930", session="REGULAR") is not None
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=2,
            remaining=0,
            evidence_version=2,
        )
    )
    assert book.virtual_latched_stop_candidate("005930").unreserved_qty == 2
    view = book.virtual_stop_obligations("005930")[0]
    monkeypatch.setattr(
        book,
        "virtual_stop_obligations",
        lambda symbol: (replace(view, state="BLOCKED_EVIDENCE"),),
    )
    before = len(book.snapshot().requests)
    assert dispatcher.drain_virtual_stop("005930", session="REGULAR") is None
    assert len(book.snapshot().requests) == before


def test_virtual_send_requires_durable_obligation_in_claim_transaction(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930", version=2, rule_kind="PRICE_AT_OR_BELOW", threshold="9800"
        ),
        expected_version=1,
    )
    buy = book.submit(
        New(
            key="protected-buy",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=4,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=2,
            remaining=2,
            evidence_version=1,
        )
    )
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    latch = book.latch_virtual_price_stop(
        "005930",
        Quote(symbol="005930", price="9700", received_at=now),
        ObserveAt(now=now, max_quote_age_seconds=2),
    )
    assert latch is not None
    sell = book.submit(
        New(
            key="virtual-stop:005930:claim",
            symbol="005930",
            side="SELL",
            config_version=2,
            qty=2,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
            stop_latch_version=latch.rule_version,
        )
    ).request
    with sqlite3.connect(path) as connection:
        connection.execute(
            "DELETE FROM outbox WHERE seq IN "
            "(SELECT seq FROM journal WHERE kind = ? AND key = ?)",
            ("stop_sell_obligation", str(sell.request_id)),
        )
        connection.execute(
            "DELETE FROM journal WHERE kind = ? AND key = ?",
            ("stop_sell_obligation", str(sell.request_id)),
        )
    dispatcher = VirtualDispatcher(book)
    views = book.virtual_stop_obligations("005930")
    assert len(views) == 1
    assert views[0].request_id == sell.request_id
    assert views[0].state == "BLOCKED_EVIDENCE"
    assert not dispatcher.send(sell.request_id, stop_session="REGULAR")
    assert dispatcher.calls == []
    assert book.transport(sell.request_id) == "INTENT_PERSISTED"
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=2,
            remaining=0,
            evidence_version=2,
        )
    )
    assert book.virtual_latched_stop_candidate("005930").unreserved_qty == 2
    assert dispatcher.drain_virtual_stop("005930", session="REGULAR") is None
    assert len(book.snapshot().requests) == 2
    later = book.submit(
        New(
            key="virtual-stop:005930:later",
            symbol="005930",
            side="SELL",
            config_version=2,
            qty=2,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
            stop_latch_version=latch.rule_version,
        )
    ).request
    assert (
        next(
            view.state
            for view in book.virtual_stop_obligations("005930")
            if view.request_id == later.request_id
        )
        == "PENDING"
    )
    assert not dispatcher.send(later.request_id, stop_session="REGULAR")
    assert book.transport(later.request_id) == "INTENT_PERSISTED"
    assert dispatcher.calls == []
    restarted = Ledger(path, lease)
    restarted_dispatcher = VirtualDispatcher(restarted)
    assert restarted_dispatcher.recover() == (buy.request_id,)
    assert restarted.virtual_stop_obligations("005930")[-1].state == "BLOCKED_EVIDENCE"
    assert restarted_dispatcher.drain_virtual_stop("005930", session="REGULAR") is None
    assert not restarted_dispatcher.send(later.request_id, stop_session="REGULAR")
    assert restarted.transport(later.request_id) == "INTENT_PERSISTED"
    assert restarted_dispatcher.calls == []


def test_cancelled_stop_obligation_requires_review_before_another_sell(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930", version=2, rule_kind="PRICE_AT_OR_BELOW", threshold="9800"
        ),
        expected_version=1,
    )
    buy = book.submit(
        New(
            key="buy-before-stop-cancel",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=4,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=4,
            remaining=0,
            evidence_version=1,
        )
    )
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    latch = book.latch_virtual_price_stop(
        "005930",
        Quote(symbol="005930", price="9700", received_at=now),
        ObserveAt(now=now, max_quote_age_seconds=2),
    )
    assert latch is not None
    dispatcher = VirtualDispatcher(book)
    sell = dispatcher.drain_virtual_stop("005930", session="REGULAR")
    assert sell is not None
    cancel = book.submit(
        Cancel(
            key="cancel-stop-sell",
            symbol="005930",
            side="SELL",
            config_version=2,
            target=sell.order_id,
            link_version=book.order(sell.order_id).link_version,
            cancel_qty=4,
        )
    ).request
    assert dispatcher.send(cancel.request_id)
    assert book.ingest(
        Cancelled(
            event_id=uuid4(),
            request_id=cancel.request_id,
            order_id=sell.order_id,
            qty=4,
            remaining=0,
            evidence_version=1,
        )
    )

    obligation = Ledger(path, lease).virtual_stop_obligations("005930")
    assert len(obligation) == 1
    assert (
        obligation[0].state,
        obligation[0].next_action,
        obligation[0].unfilled_qty,
        obligation[0].reserved_qty,
    ) == ("REVIEW_REQUIRED", "REVIEW_AND_ALERT", 4, 0)
    call_count = len(dispatcher.calls)
    assert dispatcher.drain_virtual_stop("005930", session="REGULAR") is None
    assert len(dispatcher.calls) == call_count
    restored = Ledger(path, lease)
    assert len(restored.snapshot().stop_sell_obligations) == 1
    restored_dispatcher = VirtualDispatcher(restored)
    assert restored_dispatcher.drain_virtual_stop("005930", session="REGULAR") is None
    assert restored_dispatcher.calls == []


@pytest.mark.parametrize("rejected", [False, True])
def test_failed_stop_requires_review_without_auto_retry(
    tmp_path: Path, lease: AccountLease, *, rejected: bool
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930", version=2, rule_kind="PRICE_AT_OR_BELOW", threshold="9800"
        ),
        expected_version=1,
    )
    buy = book.submit(
        New(
            key="buy-before-failure",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=2,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=2,
            remaining=0,
            evidence_version=1,
        )
    )
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    latch = book.latch_virtual_price_stop(
        "005930",
        Quote(symbol="005930", price="9700", received_at=now),
        ObserveAt(now=now, max_quote_age_seconds=2),
    )
    assert latch is not None
    sell = book.submit(
        New(
            key="virtual-stop:005930:failure",
            symbol="005930",
            side="SELL",
            config_version=2,
            qty=2,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
            stop_latch_version=latch.rule_version,
        )
    ).request
    reason = "broker-rejected" if rejected else "adapter-not-invoked"
    if rejected:
        assert book.ingest(
            Transport(event_id=uuid4(), request_id=sell.request_id, state="SENDING")
        )
    failure = (
        Rejected(event_id=uuid4(), request_id=sell.request_id, reason=reason)
        if rejected
        else SendFailed(
            event_id=uuid4(),
            request_id=sell.request_id,
            proof="NOT_INVOKED",
            reason=reason,
        )
    )
    assert book.ingest(failure)
    restored = Ledger(path, lease)
    view = restored.virtual_stop_obligations("005930")
    assert len(view) == 1
    assert (
        view[0].state,
        view[0].next_action,
        view[0].unfilled_qty,
        view[0].failure_reason,
    ) == (
        "REVIEW_REQUIRED",
        "REVIEW_AND_ALERT",
        2,
        reason,
    )
    assert (
        VirtualDispatcher(restored).drain_virtual_stop("005930", session="REGULAR")
        is None
    )
    assert len(restored.snapshot().stop_sell_obligations) == 1


def test_confirmed_order_cost_requires_every_exact_fill_price(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    buy = book.submit(
        New(
            key="priced-buy",
            symbol="005930",
            side="BUY",
            config_version=1,
            qty=3,
            order_type="LIMIT",
            price="10000",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.buy_order_average_cost(buy.order_id) is None
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=2,
            remaining=1,
            evidence_version=1,
            price="10000",
        )
    )
    assert book.buy_order_average_cost(buy.order_id) == Decimal(10000)
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=1,
            remaining=0,
            evidence_version=2,
            price="9700",
        )
    )
    assert Ledger(path, lease).buy_order_average_cost(buy.order_id) == Decimal(9900)
    for invalid in ("0", "-1", "NaN", "Infinity", " 10000", 10000.0):
        with pytest.raises(ValidationError):
            _ = Fill.model_validate(
                {
                    "event_id": str(uuid4()),
                    "order_id": str(buy.order_id),
                    "qty": 1,
                    "remaining": 0,
                    "evidence_version": 3,
                    "price": invalid,
                }
            )


def test_multiple_priced_buy_orders_share_one_basis_until_sell(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930",
            version=2,
            rule_kind="AVERAGE_COST_DROP",
            threshold="0.02",
        ),
        expected_version=1,
    )
    for index, (qty, price) in enumerate(((2, "10000"), (1, "9700")), start=1):
        buy = book.submit(
            New(
                key=f"buy-{index}",
                symbol="005930",
                side="BUY",
                config_version=2,
                qty=qty,
                order_type="MARKET",
                session="REGULAR",
                validity="DAY",
            )
        ).request
        assert book.ingest(
            Fill(
                event_id=uuid4(),
                order_id=buy.order_id,
                qty=qty,
                remaining=0,
                evidence_version=1,
                price=price,
            )
        )
    basis = Ledger(path, lease).confirmed_stop_cost_basis("005930")
    assert basis is not None
    assert (basis.qty, basis.average_cost, basis.rule_version) == (3, Decimal(9900), 2)
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    timing = ObserveAt(now=now, max_quote_age_seconds=2)
    restored = Ledger(path, lease)
    observation = restored.observe_virtual_cost_stop(
        "005930", Quote(symbol="005930", price="9700", received_at=now), timing
    )
    assert (observation.status, observation.threshold_price) == (
        "TRIGGERED",
        Decimal(9702),
    )
    stale = restored.observe_virtual_cost_stop(
        "005930",
        Quote(symbol="005930", price="9700", received_at=now - timedelta(seconds=3)),
        timing,
    )
    assert stale.reason == "QUOTE_NOT_FRESH"
    quote = Quote(symbol="005930", price="9700", received_at=now)
    first_candidate = restored.virtual_cost_stop_candidate("005930", quote, timing)
    assert (first_candidate.status, first_candidate.unreserved_qty) == ("CANDIDATE", 3)
    sell = book.submit(
        New(
            key="sell-after-buys",
            symbol="005930",
            side="SELL",
            config_version=2,
            qty=1,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    reserved_candidate = book.virtual_cost_stop_candidate("005930", quote, timing)
    assert (reserved_candidate.status, reserved_candidate.unreserved_qty) == (
        "CANDIDATE",
        2,
    )
    assert book.ingest(
        Transport(event_id=uuid4(), request_id=sell.request_id, state="UNKNOWN")
    )
    uncertain_candidate = Ledger(path, lease).virtual_cost_stop_candidate(
        "005930", quote, timing
    )
    assert (
        uncertain_candidate.status,
        uncertain_candidate.reason,
        uncertain_candidate.unreserved_qty,
    ) == ("BLOCKED", "SELL_EVIDENCE_UNRESOLVED", 0)
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=sell.order_id,
            qty=1,
            remaining=0,
            evidence_version=1,
            price="9700",
        )
    )
    assert Ledger(path, lease).confirmed_stop_cost_basis("005930") is None
    blocked = Ledger(path, lease).observe_virtual_cost_stop("005930", None, timing)
    assert blocked.reason == "COST_EVIDENCE_INCOMPLETE"


def test_preexisting_holdings_cannot_acquire_inferred_cost(
    tmp_path: Path, lease: AccountLease
) -> None:
    book = Ledger(tmp_path / "ledger.sqlite3", lease)
    book.approve_virtual_reconciliation(0)
    book.allocate(Allocation(symbol="005930", qty=1))
    assert book.confirmed_stop_cost_basis("005930") is None


def test_quote_ingress_blocks_replay_reverse_order_and_restarts_safely(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.apply_virtual_stop_config(
        VirtualStopBinding(
            symbol="005930",
            version=2,
            rule_kind="PRICE_AT_OR_BELOW",
            threshold="9800",
        ),
        expected_version=1,
    )
    buy = book.submit(
        New(
            key="quote-ingress-buy",
            symbol="005930",
            side="BUY",
            config_version=2,
            qty=7,
            order_type="MARKET",
            session="REGULAR",
            validity="DAY",
        )
    ).request
    assert book.ingest(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=4,
            remaining=3,
            evidence_version=1,
        )
    )
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    timing = ObserveAt(now=now, max_quote_age_seconds=2)

    first = Quote(
        symbol="005930", price="9900", received_at=now - timedelta(milliseconds=500)
    )
    observed = book.process_virtual_stop_quote("005930", first, timing)
    assert (observed.accepted, observed.observation.status, observed.latch) == (
        True,
        "NOT_TRIGGERED",
        None,
    )

    stale = book.process_virtual_stop_quote(
        "005930",
        Quote(symbol="005930", price="9000", received_at=now - timedelta(seconds=3)),
        timing,
    )
    assert (stale.accepted, stale.observation.reason) == (False, "QUOTE_NOT_FRESH")

    clock_reversed = book.process_virtual_stop_quote(
        "005930",
        Quote(
            symbol="005930",
            price="9700",
            received_at=now - timedelta(milliseconds=200),
        ),
        ObserveAt(now=now - timedelta(milliseconds=100), max_quote_age_seconds=2),
    )
    assert (clock_reversed.accepted, clock_reversed.observation.reason) == (
        False,
        "EVALUATION_TIME_REVERSED",
    )

    reversed_quote = Quote(
        symbol="005930", price="9700", received_at=now - timedelta(seconds=1)
    )
    reversed_result = book.process_virtual_stop_quote("005930", reversed_quote, timing)
    assert (reversed_result.accepted, reversed_result.observation.reason) == (
        False,
        "QUOTE_OUT_OF_ORDER",
    )
    duplicate = book.process_virtual_stop_quote("005930", first, timing)
    assert (duplicate.accepted, duplicate.observation.reason) == (
        False,
        "QUOTE_DUPLICATE",
    )

    triggered_quote = Quote(
        symbol="005930", price="9700", received_at=now - timedelta(milliseconds=250)
    )
    triggered = book.process_virtual_stop_quote("005930", triggered_quote, timing)
    assert triggered.accepted
    assert triggered.observation.status == "TRIGGERED"
    assert triggered.latch is not None
    assert book.virtual_latched_stop_candidate("005930").unreserved_qty == 4

    restored = Ledger(path, lease)
    repeated = restored.process_virtual_stop_quote("005930", triggered_quote, timing)
    assert (repeated.accepted, repeated.observation.reason) == (
        False,
        "QUOTE_DUPLICATE",
    )
    assert restored.snapshot().stop_latches == (triggered.latch,)
    assert restored.snapshot().stop_sell_obligations == ()
    assert VirtualDispatcher(restored).real_order_transport_available is False

    future = Quote(
        symbol="005930", price="9000", received_at=now + timedelta(milliseconds=1)
    )
    future_result = restored.process_virtual_stop_quote("005930", future, timing)
    assert (future_result.accepted, future_result.observation.reason) == (
        False,
        "QUOTE_NOT_FRESH",
    )
    wrong_symbol = Quote(
        symbol="000660", price="9000", received_at=now - timedelta(milliseconds=100)
    )
    wrong_result = restored.process_virtual_stop_quote("005930", wrong_symbol, timing)
    assert (wrong_result.accepted, wrong_result.observation.reason) == (
        False,
        "QUOTE_MISSING_OR_WRONG_SYMBOL",
    )
