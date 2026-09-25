import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from execution.facts import Fill, Transport
from execution.ledger import Ledger
from execution.models import LedgerError, New
from execution.ownership import AccountLease
from execution.virtual import VirtualDispatcher
from tests.conftest import Scenario


def test_single_submission_when_two_writers_use_same_key(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    command = New(
        key="same-intent",
        symbol="005930",
        side="SELL",
        qty=100,
        config_version=1,
        order_type="MARKET",
        session="REGULAR",
        validity="DAY",
    )
    # When
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(scenario.book.submit, [command, command]))
    # Then
    assert sum(result.created for result in results) == 1
    assert results[0].request.request_id == results[1].request.request_id
    assert scenario.book.portfolio("005930").reserved == 100


def test_single_call_when_two_dispatchers_claim_same_request(
    scenario: Scenario,
) -> None:
    # Given
    scenario.allocate(100)
    command = New(
        key="same-send",
        symbol="005930",
        side="SELL",
        qty=100,
        config_version=1,
        order_type="MARKET",
        session="REGULAR",
        validity="DAY",
    )
    request = scenario.book.submit(command).request
    first = VirtualDispatcher(scenario.book)
    second = VirtualDispatcher(scenario.book)
    # When
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(first.send, request.request_id)
        two = pool.submit(second.send, request.request_id)
        results = (one.result(), two.result())
    # Then
    assert sum(results) == 1
    assert len(first.calls) + len(second.calls) == 1


def test_fill_effects_rollback_when_outbox_insert_fails(scenario: Scenario) -> None:
    # Given
    buy = scenario.new("BUY", 100)
    before = scenario.book.snapshot()
    with closing(sqlite3.connect(scenario.book.storage.path)) as connection, connection:
        _ = connection.execute(
            """CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox
            BEGIN SELECT RAISE(ABORT, 'test failure'); END"""
        )
    fact = Fill(
        event_id=uuid4(),
        order_id=buy.order_id,
        qty=30,
        remaining=70,
        evidence_version=1,
    )
    # When
    with pytest.raises(sqlite3.IntegrityError, match="test failure"):
        _ = scenario.book.ingest(fact)
    # Then
    assert scenario.book.snapshot() == before
    position = scenario.book.portfolio("005930")
    assert (position.managed, position.protected, position.liquidation) == (0, 0, 0)


def test_reconciliation_when_process_dies_after_claim(scenario: Scenario) -> None:
    # Given
    command = New(
        key="interrupted-send",
        symbol="005930",
        side="BUY",
        qty=100,
        config_version=1,
        order_type="MARKET",
        session="REGULAR",
        validity="DAY",
    )
    request = scenario.book.submit(command).request
    _ = scenario.book.ingest(
        Transport(event_id=uuid4(), request_id=request.request_id, state="SENDING")
    )
    restored = Ledger(
        scenario.book.storage.path,
        scenario.book.storage.lease,
    )
    dispatcher = VirtualDispatcher(restored)
    # When
    unresolved = dispatcher.recover()
    attempted = dispatcher.send(request.request_id)
    # Then
    assert unresolved == (request.request_id,)
    assert restored.transport(request.request_id) == "UNKNOWN"
    assert not attempted
    assert dispatcher.calls == []


def test_uncertainty_when_acknowledged_cancel_has_no_effect(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    cancel = scenario.cancel(sell, 100)
    scenario.dispatcher.acknowledge(cancel)
    # When
    unresolved = scenario.dispatcher.recover()
    # Then
    assert cancel.request_id in unresolved
    assert scenario.book.portfolio("005930").reserved == 100
    assert scenario.book.transport(cancel.request_id) == "ACKED"


def test_existing_database_rejected_when_schema_is_unrelated(
    tmp_path: Path, lease: AccountLease
) -> None:
    # Given: a test DB standing in for a database the new engine does not own.
    path = tmp_path / "unrelated.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        _ = connection.execute("CREATE TABLE unrelated (value TEXT)")
    # When / Then
    with pytest.raises(LedgerError, match="UNRECOGNIZED_DATABASE"):
        _ = Ledger(path, lease)


def test_schema_version_rejected_when_database_is_from_future(
    scenario: Scenario,
) -> None:
    # Given
    with closing(sqlite3.connect(scenario.book.storage.path)) as connection, connection:
        _ = connection.execute("PRAGMA user_version = 3")
    scope = scenario.book.storage.lease
    # When / Then
    with pytest.raises(LedgerError, match="UNSUPPORTED_SCHEMA_VERSION"):
        _ = Ledger(scenario.book.storage.path, scope)


def test_schema_v1_migrates_quote_cursor_table_transactionally(
    tmp_path: Path, lease: AccountLease
) -> None:
    path = tmp_path / "v1.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        _ = connection.execute(
            """CREATE TABLE journal (
            seq INTEGER PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL,
            key TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(scope, kind, key))"""
        )
        _ = connection.execute(
            """CREATE TABLE outbox (
            seq INTEGER PRIMARY KEY REFERENCES journal(seq), payload TEXT NOT NULL)"""
        )
        _ = connection.execute(
            """CREATE TRIGGER publish AFTER INSERT ON journal BEGIN
            INSERT INTO outbox(seq, payload) VALUES (NEW.seq, NEW.payload); END"""
        )
        _ = connection.execute("PRAGMA user_version = 1")

    _ = Ledger(path, lease)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute(
            """SELECT count(*) FROM sqlite_master
            WHERE type='table' AND name='stop_quote_cursors'"""
        ).fetchone() == (1,)
