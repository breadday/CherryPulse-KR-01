"""Durable, inert stop rule binding in the virtual ledger."""

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from execution.facts import Fill
from execution.ledger import Ledger
from execution.models import Allocation, LedgerError, New, VirtualStopBinding
from execution.ownership import AccountLease


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


def test_preexisting_holdings_cannot_acquire_inferred_cost(
    tmp_path: Path, lease: AccountLease
) -> None:
    book = Ledger(tmp_path / "ledger.sqlite3", lease)
    book.approve_virtual_reconciliation(0)
    book.allocate(Allocation(symbol="005930", qty=1))
    assert book.confirmed_stop_cost_basis("005930") is None
