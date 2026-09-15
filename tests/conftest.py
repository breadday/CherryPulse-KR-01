from collections.abc import Generator
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest

from execution.facts import Amended, Cancelled, Fill, Transport
from execution.ledger import Ledger
from execution.models import Allocation, Amend, Cancel, Control, New, Request, Scope
from execution.ownership import AccountLease, account_lock
from execution.virtual import VirtualDispatcher


class Scenario:
    """Mutable virtual call recorder around the real SQLite boundary."""

    def __init__(self, path: Path, lease: AccountLease) -> None:
        self.book: Ledger = Ledger(path, lease)
        self.book.approve_virtual_reconciliation(0)
        self.dispatcher: VirtualDispatcher = VirtualDispatcher(self.book)
        self.version: int = 0

    def allocate(self, qty: int) -> None:
        self.book.allocate(Allocation(symbol="005930", qty=qty))

    def new(self, side: Literal["BUY", "SELL"], qty: int) -> Request:
        command = New(
            key=str(uuid4()),
            symbol="005930",
            side=side,
            config_version=1,
            qty=qty,
            order_type="LIMIT",
            price="10000",
            session="REGULAR",
            validity="DAY",
        )
        request = self.book.submit(command).request
        assert self.dispatcher.send(request.request_id)
        self.dispatcher.acknowledge(request)
        return request

    def cancel(self, request: Request, qty: int) -> Request:
        command = Cancel(
            key=str(uuid4()),
            symbol="005930",
            side=request.command.side,
            config_version=1,
            target=request.order_id,
            link_version=self.book.order(request.order_id).link_version,
            cancel_qty=qty,
        )
        result = self.book.submit(command).request
        assert self.dispatcher.send(result.request_id)
        return result

    def amend(self, request: Request, delta: int) -> Request:
        command = Amend(
            key=str(uuid4()),
            symbol="005930",
            side=request.command.side,
            config_version=1,
            target=request.order_id,
            link_version=self.book.order(request.order_id).link_version,
            qty_delta=delta,
        )
        result = self.book.submit(command).request
        _ = self.dispatcher.send(result.request_id)
        return result

    def fill(self, request: Request, quantities: tuple[int, int]) -> Fill:
        self.version += 1
        fact = Fill(
            event_id=uuid4(),
            order_id=request.order_id,
            qty=quantities[0],
            remaining=quantities[1],
            evidence_version=self.version,
        )
        assert self.book.ingest(fact)
        return fact

    def cancelled(self, request: Request, quantities: tuple[int, int]) -> Cancelled:
        self.version += 1
        fact = Cancelled(
            event_id=uuid4(),
            request_id=request.request_id,
            order_id=request.order_id,
            qty=quantities[0],
            remaining=quantities[1],
            evidence_version=self.version,
        )
        assert self.book.ingest(fact)
        return fact

    def amended(self, request: Request, quantities: tuple[int, int]) -> None:
        self.version += 1
        assert self.book.ingest(
            Amended(
                event_id=uuid4(),
                request_id=request.request_id,
                order_id=request.order_id,
                qty_delta=quantities[0],
                remaining=quantities[1],
                evidence_version=self.version,
            )
        )

    def unknown(self, request: Request) -> None:
        assert self.book.ingest(
            Transport(event_id=uuid4(), request_id=request.request_id, state="UNKNOWN")
        )

    def liquidate(self) -> None:
        self.book.control(
            Control(symbol="005930", entry_stopped=True, liquidating=True)
        )

    def counts(self) -> tuple[int, int, int]:
        kinds = [r.command.kind for r in self.dispatcher.calls]
        return kinds.count("NEW"), kinds.count("AMEND"), kinds.count("CANCEL")

    def replay(self) -> None:
        before = self.book.snapshot()
        for request in before.requests:
            assert not self.book.submit(request.command).created
            assert not self.dispatcher.send(request.request_id)
        for fact in before.facts:
            assert not self.book.ingest(fact)
        assert self.book.snapshot() == before


@pytest.fixture
def lease(tmp_path: Path) -> Generator[AccountLease, None, None]:
    scope = Scope(account_id="DEMO", environment="PAPER", execution_scope=uuid4())
    with account_lock(tmp_path / "locks", scope) as acquired:
        yield acquired


@pytest.fixture
def scenario(tmp_path: Path, lease: AccountLease) -> Scenario:
    return Scenario(tmp_path / "ledger.sqlite3", lease)
