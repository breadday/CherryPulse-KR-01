# pyright: reportUnreachable=false
"""STEP 03 stop-loss priority flow without a brokerage connection."""

import sys
from collections.abc import Generator
from pathlib import Path
from types import ModuleType
from typing import Literal
from uuid import uuid4

import pytest
from pydantic import ValidationError

if sys.platform != "win32":
    msvcrt = ModuleType("msvcrt")
    msvcrt.LK_NBLCK = 1  # type: ignore[attr-defined]
    msvcrt.locking = lambda _fd, _mode, _size: None  # type: ignore[attr-defined]
    sys.modules.setdefault("msvcrt", msvcrt)

from execution.facts import Fill, SendFailed, StopLossTriggered
from execution.ledger import Ledger, Submission
from execution.models import (
    Allocation,
    LedgerError,
    New,
    OrderCommand,
    Request,
    Scope,
)
from execution.ownership import AccountLease
from execution.virtual import VirtualDispatcher


@pytest.fixture
def runtime(tmp_path: Path) -> Generator[tuple[Ledger, VirtualDispatcher], None, None]:
    """Open one isolated PAPER ledger while preserving the production lease boundary."""
    scope = Scope(account_id="STEP03", environment="PAPER", execution_scope=uuid4())
    with AccountLease.acquire(tmp_path / "locks", scope) as lease:
        book = Ledger(tmp_path / "ledger.sqlite3", lease)
        book.approve_virtual_reconciliation(0)
        yield book, VirtualDispatcher(book)


def new_command(
    key: str,
    side: Literal["BUY", "SELL"],
    qty: int,
    *,
    order_type: Literal["LIMIT", "MARKET"] = "LIMIT",
) -> New:
    """Build one explicit virtual order without exchange defaults."""
    return New(
        key=key,
        symbol="005930",
        side=side,
        config_version=1,
        qty=qty,
        order_type=order_type,
        price="10000" if order_type == "LIMIT" else None,
        session="REGULAR",
        validity="DAY",
    )


def submit(
    book: Ledger,
    dispatcher: VirtualDispatcher,
    command: New,
    *,
    acknowledge: bool = True,
) -> Request:
    """Persist and virtually send one order, optionally leaving transport unresolved."""
    request = book.submit(command).request
    assert dispatcher.send(request.request_id)
    if acknowledge:
        dispatcher.acknowledge(request)
    return request


def stop_trigger() -> StopLossTriggered:
    """Return a confirmed virtual stop condition for the baseline config."""
    return StopLossTriggered(
        event_id=uuid4(),
        symbol="005930",
        config_version=1,
        observed_price="9000",
        threshold_price="9500",
    )


def sell_calls(dispatcher: VirtualDispatcher) -> list[New]:
    """Return only NEW sell commands from the virtual adapter surface."""
    return [
        command
        for request in dispatcher.calls
        if isinstance(command := request.command, New) and command.side == "SELL"
    ]


def test_stop_loss_trigger_liquidates_confirmed_partial_fill(
    runtime: tuple[Ledger, VirtualDispatcher],
) -> None:
    book, dispatcher = runtime
    buy = submit(book, dispatcher, new_command("step03-buy", "BUY", 100))
    dispatcher.process(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=40,
            remaining=60,
            evidence_version=1,
        )
    )

    trigger = stop_trigger()
    dispatcher.process(trigger)
    dispatcher.process(trigger)

    with pytest.raises(LedgerError, match="ENTRY_BLOCKED"):
        _ = book.submit(
            new_command("step03-buy-after-stop", "BUY", 1, order_type="MARKET")
        )

    position = book.portfolio("005930")
    sells = sell_calls(dispatcher)
    assert (position.protected, position.liquidation, position.reserved) == (40, 40, 40)
    assert position.entry_stopped
    assert position.liquidating
    assert len(sells) == 1
    assert sells[0].qty == 40
    assert sells[0].order_type == "MARKET"


def test_stop_loss_stays_active_for_a_late_buy_fill(
    runtime: tuple[Ledger, VirtualDispatcher],
) -> None:
    book, dispatcher = runtime
    buy = submit(book, dispatcher, new_command("step03-late-buy", "BUY", 100))

    dispatcher.process(stop_trigger())
    assert book.portfolio("005930").liquidating

    dispatcher.process(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=20,
            remaining=80,
            evidence_version=1,
        )
    )

    position = book.portfolio("005930")
    sells = sell_calls(dispatcher)
    assert (position.managed, position.reserved, position.liquidation) == (20, 20, 20)
    assert len(sells) == 1
    assert sells[0].qty == 20


def test_stop_loss_does_not_duplicate_an_unresolved_sell(
    runtime: tuple[Ledger, VirtualDispatcher],
) -> None:
    book, dispatcher = runtime
    book.allocate(Allocation(symbol="005930", qty=40))
    _ = submit(
        book,
        dispatcher,
        new_command("step03-existing-sell", "SELL", 20, order_type="MARKET"),
        acknowledge=False,
    )

    dispatcher.process(stop_trigger())

    position = book.portfolio("005930")
    assert (position.managed, position.reserved, position.liquidation) == (40, 20, 40)
    assert position.sell_uncertain
    assert position.reconciliation_required
    assert position.available == 0
    assert len(sell_calls(dispatcher)) == 1


def test_stop_loss_ignores_a_proven_unsent_historical_sell(
    runtime: tuple[Ledger, VirtualDispatcher],
) -> None:
    book, dispatcher = runtime
    book.allocate(Allocation(symbol="005930", qty=40))
    failed = book.submit(
        new_command("step03-proven-unsent-sell", "SELL", 40, order_type="MARKET")
    ).request
    dispatcher.process(
        SendFailed(
            event_id=uuid4(),
            request_id=failed.request_id,
            proof="NOT_INVOKED",
            reason="LOCAL_TEST_PROOF",
        )
    )

    dispatcher.process(stop_trigger())

    sells = sell_calls(dispatcher)
    assert len(sells) == 1
    assert sells[0].key.startswith("liquidation:005930:")
    assert sells[0].qty == 40


def test_ledger_ingress_drains_a_late_fill_after_stop_loss(
    runtime: tuple[Ledger, VirtualDispatcher],
) -> None:
    book, dispatcher = runtime
    buy = submit(book, dispatcher, new_command("step03-direct-ingress-buy", "BUY", 100))
    dispatcher.calls.clear()

    assert book.ingest_json(stop_trigger().model_dump_json())
    assert sell_calls(dispatcher) == []

    late_fill = Fill(
        event_id=uuid4(),
        order_id=buy.order_id,
        qty=20,
        remaining=80,
        evidence_version=1,
    )
    assert book.ingest_json(late_fill.model_dump_json())

    sells = sell_calls(dispatcher)
    assert len(sells) == 1
    assert sells[0].qty == 20


def test_duplicate_trigger_retries_drain_after_session_approval(tmp_path: Path) -> None:
    scope = Scope(
        account_id="STEP03-RETRY", environment="PAPER", execution_scope=uuid4()
    )
    database = tmp_path / "retry-ledger.sqlite3"
    locks = tmp_path / "retry-locks"
    with AccountLease.acquire(locks, scope) as lease:
        setup = Ledger(database, lease)
        setup.approve_virtual_reconciliation(0)
        setup.allocate(Allocation(symbol="005930", qty=40))

    with AccountLease.acquire(locks, scope) as lease:
        book = Ledger(database, lease)
        dispatcher = VirtualDispatcher(book)
        trigger = stop_trigger()

        with pytest.raises(LedgerError, match="SESSION_RECONCILIATION_REQUIRED"):
            _ = book.ingest(trigger)

        assert book.portfolio("005930").available == 40
        assert sell_calls(dispatcher) == []
        book.approve_virtual_reconciliation(book.snapshot().revision)

        assert not book.ingest(trigger)
        sells = sell_calls(dispatcher)
        assert len(sells) == 1
        assert sells[0].qty == 40


def test_duplicate_trigger_retries_drain_after_config_race(
    runtime: tuple[Ledger, VirtualDispatcher], monkeypatch: pytest.MonkeyPatch
) -> None:
    book, dispatcher = runtime
    book.allocate(Allocation(symbol="005930", qty=40))
    original_submit = book.submit
    advanced = False

    def advance_config_before_submit(command: OrderCommand) -> Submission:
        nonlocal advanced
        if (
            isinstance(command, New)
            and command.key.startswith("liquidation:")
            and not advanced
        ):
            advanced = True
            book.apply_config("005930", expected_version=1, version=2)
        return original_submit(command)

    monkeypatch.setattr(book, "submit", advance_config_before_submit)
    trigger = stop_trigger()

    with pytest.raises(LedgerError, match="STALE_CONFIG_VERSION"):
        _ = book.ingest(trigger)

    assert book.portfolio("005930").available == 40
    assert sell_calls(dispatcher) == []
    assert not book.ingest(trigger)

    sells = sell_calls(dispatcher)
    assert len(sells) == 1
    assert sells[0].config_version == 2
    assert sells[0].qty == 40


def test_liquidation_recovers_when_config_advances_after_submit(
    runtime: tuple[Ledger, VirtualDispatcher], monkeypatch: pytest.MonkeyPatch
) -> None:
    book, dispatcher = runtime
    book.allocate(Allocation(symbol="005930", qty=40))
    original_send = dispatcher.send
    advanced = False

    def advance_config_before_send(request_id: object) -> bool:
        nonlocal advanced
        request = next(
            request
            for request in book.snapshot().requests
            if request.request_id == request_id
        )
        if (
            isinstance(request.command, New)
            and request.command.key.startswith("liquidation:")
            and not advanced
        ):
            advanced = True
            book.apply_config("005930", expected_version=1, version=2)
        return original_send(request.request_id)

    monkeypatch.setattr(dispatcher, "send", advance_config_before_send)
    trigger = stop_trigger()

    dispatcher.process(trigger)
    dispatcher.process(trigger)

    sells = sell_calls(dispatcher)
    assert len(sells) == 1
    assert sells[0].config_version == 2
    assert sells[0].qty == 40
    assert book.portfolio("005930").reserved == 40


def test_replayed_trigger_sends_a_persisted_liquidation_intent(tmp_path: Path) -> None:
    scope = Scope(
        account_id="STEP03-PERSISTED",
        environment="PAPER",
        execution_scope=uuid4(),
    )
    with AccountLease.acquire(tmp_path / "persisted-locks", scope) as lease:
        book = Ledger(tmp_path / "persisted-ledger.sqlite3", lease)
        book.approve_virtual_reconciliation(0)
        book.allocate(Allocation(symbol="005930", qty=40))
        trigger = stop_trigger()
        assert book.ingest(trigger)
        persisted = book.submit(
            new_command(
                "liquidation:005930:persisted",
                "SELL",
                40,
                order_type="MARKET",
            )
        ).request
        dispatcher = VirtualDispatcher(book)

        assert not book.ingest(trigger)

        sells = sell_calls(dispatcher)
        assert len(sells) == 1
        assert sells[0] == persisted.command
        assert book.portfolio("005930").reserved == 40


def test_replayed_trigger_does_not_send_persisted_intent_after_quantity_conflict(
    tmp_path: Path,
) -> None:
    scope = Scope(
        account_id="STEP03-PERSISTED-CONFLICT",
        environment="PAPER",
        execution_scope=uuid4(),
    )
    with AccountLease.acquire(tmp_path / "conflict-locks", scope) as lease:
        book = Ledger(tmp_path / "conflict-ledger.sqlite3", lease)
        book.approve_virtual_reconciliation(0)
        book.allocate(Allocation(symbol="005930", qty=40))
        historical = book.submit(
            new_command("step03-historical-unsent", "SELL", 20, order_type="MARKET")
        ).request
        assert book.ingest(
            SendFailed(
                event_id=uuid4(),
                request_id=historical.request_id,
                proof="NOT_INVOKED",
                reason="LOCAL_TEST_PROOF",
            )
        )
        trigger = stop_trigger()
        assert book.ingest(trigger)
        _ = book.submit(
            new_command(
                "liquidation:005930:persisted-conflict",
                "SELL",
                40,
                order_type="MARKET",
            )
        )
        assert book.ingest(
            Fill(
                event_id=uuid4(),
                order_id=historical.order_id,
                qty=20,
                remaining=0,
                evidence_version=1,
            )
        )
        position = book.portfolio("005930")
        assert (position.managed, position.reserved, position.available) == (20, 40, 0)
        assert position.reconciliation_required
        dispatcher = VirtualDispatcher(book)

        assert not book.ingest(trigger)

        assert sell_calls(dispatcher) == []
        assert book.portfolio("005930").reconciliation_required


def test_stop_loss_does_not_sell_through_a_quantity_gap(
    runtime: tuple[Ledger, VirtualDispatcher],
) -> None:
    book, dispatcher = runtime
    buy = submit(book, dispatcher, new_command("step03-gap-buy", "BUY", 100))
    dispatcher.process(
        Fill(
            event_id=uuid4(),
            order_id=buy.order_id,
            qty=40,
            remaining=50,
            evidence_version=1,
        )
    )

    dispatcher.process(stop_trigger())

    position = book.portfolio("005930")
    assert book.order(buy.order_id).gap == 10
    assert (position.managed, position.reserved, position.liquidation) == (40, 0, 40)
    assert position.reconciliation_required
    assert position.available == 0
    assert sell_calls(dispatcher) == []


def test_stop_loss_trigger_rejects_price_above_threshold() -> None:
    with pytest.raises(ValidationError, match="STOP_LOSS_NOT_TRIGGERED"):
        _ = StopLossTriggered(
            event_id=uuid4(),
            symbol="005930",
            config_version=1,
            observed_price="9600",
            threshold_price="9500",
        )


def test_stop_loss_trigger_rejects_stale_config_version(
    runtime: tuple[Ledger, VirtualDispatcher],
) -> None:
    book, dispatcher = runtime
    book.apply_config("005930", expected_version=1, version=2)

    with pytest.raises(LedgerError, match="STALE_CONFIG_VERSION"):
        dispatcher.process(stop_trigger())

    assert not book.portfolio("005930").liquidating
    assert dispatcher.calls == []
