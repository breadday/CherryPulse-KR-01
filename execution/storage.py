"""Append-only SQLite journal and transactional outbox for virtual execution."""

import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from pydantic import TypeAdapter
from typing_extensions import assert_never

from execution.facts import FACT, Fact
from execution.models import (
    Allocation,
    AppliedConfig,
    Control,
    LedgerError,
    Request,
    StopLatch,
    StopQuoteCheckpoint,
    StopRuleAssignment,
    StopSellObligation,
    VirtualStopBinding,
)
from execution.ownership import AccountLease

EntryKind = Literal[
    "request",
    "fact",
    "allocation",
    "control",
    "config",
    "stop_binding",
    "stop_assignment",
    "stop_latch",
    "stop_sell_obligation",
]
ROWS: Final = TypeAdapter(list[tuple[EntryKind, str, str]])
COUNTS: Final = TypeAdapter(list[tuple[int]])
SCHEMA_VERSION: Final = 2
SCHEMA_OBJECTS: Final = 4
SCHEMA_V1_OBJECTS: Final = 3
SCHEMA: Final = (
    """CREATE TABLE journal (
      seq INTEGER PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL,
      key TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(scope, kind, key))""",
    """CREATE TABLE outbox (
      seq INTEGER PRIMARY KEY REFERENCES journal(seq), payload TEXT NOT NULL)""",
    """CREATE TRIGGER publish AFTER INSERT ON journal BEGIN
      INSERT INTO outbox(seq, payload) VALUES (NEW.seq, NEW.payload); END""",
    """CREATE TABLE stop_quote_cursors (
      scope TEXT NOT NULL, symbol TEXT NOT NULL, price TEXT NOT NULL,
      received_at TEXT NOT NULL, evaluated_at TEXT NOT NULL,
      PRIMARY KEY(scope, symbol))""",
    "PRAGMA user_version = 2",
)


@dataclass(frozen=True, slots=True)
class Journal:
    """Typed complete scope snapshot inside one read or write transaction."""

    requests: tuple[Request, ...]
    facts: tuple[Fact, ...]
    allocations: tuple[Allocation, ...]
    controls: tuple[Control, ...]
    configs: tuple[AppliedConfig, ...] = ()
    stop_bindings: tuple[VirtualStopBinding, ...] = ()
    stop_assignments: tuple[StopRuleAssignment, ...] = ()
    stop_latches: tuple[StopLatch, ...] = ()
    stop_quotes: tuple[StopQuoteCheckpoint, ...] = ()
    stop_sell_obligations: tuple[StopSellObligation, ...] = ()

    @property
    def revision(self) -> int:
        """Count committed scope entries for exact local reconciliation review."""
        return (
            len(self.requests)
            + len(self.facts)
            + len(self.allocations)
            + len(self.controls)
            + len(self.configs)
            + len(self.stop_bindings)
            + len(self.stop_assignments)
            + len(self.stop_latches)
            + len(self.stop_sell_obligations)
        )


@dataclass(frozen=True, slots=True)
class Entry:
    """A unique immutable journal entry."""

    kind: EntryKind
    key: str
    payload: str


class Storage:
    """Own connections per operation; BEGIN IMMEDIATE serializes all writers."""

    def __init__(self, path: Path, lease: AccountLease) -> None:
        """Initialize a new journal or recognize an existing simulator schema."""
        lease.bind_database(path)
        self.path: Path = path
        self.lease: AccountLease = lease
        self.scope: str = lease.scope.model_dump_json()
        with (
            lease.operation(),
            closing(sqlite3.connect(path, timeout=10)) as connection,
            connection,
        ):
            _ = connection.execute("BEGIN IMMEDIATE")
            tables = COUNTS.validate_python(
                connection.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table'",
                ).fetchall()
            )[0][0]
            if tables == 0:
                for statement in SCHEMA:
                    _ = connection.execute(statement)
            else:
                names = connection.execute(
                    """SELECT count(*) FROM sqlite_master
                    WHERE name IN (
                    'journal','outbox','publish','stop_quote_cursors')""",
                ).fetchall()
                object_count = COUNTS.validate_python(names)[0][0]
                version = COUNTS.validate_python(
                    connection.execute("PRAGMA user_version").fetchall()
                )[0][0]
                if version == 1 and object_count == SCHEMA_V1_OBJECTS:
                    _ = connection.execute(
                        """CREATE TABLE stop_quote_cursors (
                        scope TEXT NOT NULL, symbol TEXT NOT NULL, price TEXT NOT NULL,
                        received_at TEXT NOT NULL, evaluated_at TEXT NOT NULL,
                        PRIMARY KEY(scope, symbol))"""
                    )
                    _ = connection.execute("PRAGMA user_version = 2")
                    object_count = SCHEMA_OBJECTS
                    version = SCHEMA_VERSION
                if object_count != SCHEMA_OBJECTS:
                    raise LedgerError("UNRECOGNIZED_DATABASE")
                if version != SCHEMA_VERSION:
                    raise LedgerError("UNSUPPORTED_SCHEMA_VERSION")

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Commit the entire operation or roll it back, including its outbox."""
        with (
            self.lease.operation(),
            closing(sqlite3.connect(self.path, timeout=10)) as connection,
            connection,
        ):
            _ = connection.execute("BEGIN IMMEDIATE")
            yield connection

    def read(self, connection: sqlite3.Connection) -> Journal:  # noqa: C901
        """Parse stored JSON at the database trust boundary."""
        rows = ROWS.validate_python(
            connection.execute(
                "SELECT kind,key,payload FROM journal WHERE scope=? ORDER BY seq",
                (self.scope,),
            ).fetchall()
        )
        requests: list[Request] = []
        facts: list[Fact] = []
        allocations: list[Allocation] = []
        controls: list[Control] = []
        configs: list[AppliedConfig] = []
        stop_bindings: list[VirtualStopBinding] = []
        stop_assignments: list[StopRuleAssignment] = []
        stop_latches: list[StopLatch] = []
        stop_quotes = [
            StopQuoteCheckpoint(
                symbol=symbol,
                price=price,
                received_at=received_at,
                evaluated_at=evaluated_at,
            )
            for symbol, price, received_at, evaluated_at in connection.execute(
                """SELECT symbol,price,received_at,evaluated_at
                FROM stop_quote_cursors WHERE scope=? ORDER BY symbol""",
                (self.scope,),
            ).fetchall()
        ]
        stop_sell_obligations: list[StopSellObligation] = []
        for kind, _, payload in rows:
            match kind:
                case "request":
                    requests.append(Request.model_validate_json(payload))
                case "fact":
                    facts.append(FACT.validate_json(payload))
                case "allocation":
                    allocations.append(Allocation.model_validate_json(payload))
                case "control":
                    controls.append(Control.model_validate_json(payload))
                case "config":
                    configs.append(AppliedConfig.model_validate_json(payload))
                case "stop_binding":
                    stop_bindings.append(
                        VirtualStopBinding.model_validate_json(payload)
                    )
                case "stop_assignment":
                    stop_assignments.append(
                        StopRuleAssignment.model_validate_json(payload)
                    )
                case "stop_latch":
                    stop_latches.append(StopLatch.model_validate_json(payload))
                case "stop_sell_obligation":
                    stop_sell_obligations.append(
                        StopSellObligation.model_validate_json(payload)
                    )
                case _:
                    assert_never(kind)
        return Journal(
            tuple(requests),
            tuple(facts),
            tuple(allocations),
            tuple(controls),
            tuple(configs),
            tuple(stop_bindings),
            tuple(stop_assignments),
            tuple(stop_latches),
            tuple(stop_quotes),
            tuple(stop_sell_obligations),
        )

    def append(self, connection: sqlite3.Connection, entry: Entry) -> None:
        """Publish one new domain entry and its outbox payload atomically."""
        _ = connection.execute(
            "INSERT INTO journal(scope,kind,key,payload) VALUES(?,?,?,?)",
            (self.scope, entry.kind, entry.key, entry.payload),
        )

    def checkpoint_stop_quote(
        self, connection: sqlite3.Connection, checkpoint: StopQuoteCheckpoint
    ) -> None:
        """Keep one monotonic cursor per symbol without journaling every market tick."""
        _ = connection.execute(
            """INSERT INTO stop_quote_cursors
            (scope,symbol,price,received_at,evaluated_at) VALUES(?,?,?,?,?)
            ON CONFLICT(scope,symbol) DO UPDATE SET
            price=excluded.price, received_at=excluded.received_at,
            evaluated_at=excluded.evaluated_at""",
            (
                self.scope,
                checkpoint.symbol,
                str(checkpoint.price),
                checkpoint.received_at.isoformat(),
                checkpoint.evaluated_at.isoformat(),
            ),
        )
