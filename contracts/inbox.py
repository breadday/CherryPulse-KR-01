"""Durable desired-settings inbox, with no access to the trading ledger."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from contracts.settings import Actor, ConfigCommand, Decision, decide, digest


class CommandConflictError(ValueError):
    """The same command identity has been reused with different content."""


class ConfigInbox:
    """Persist an authenticated decision before returning an acknowledgement."""

    def __init__(self, path: Path) -> None:
        """Create an isolated settings inbox, never opening an operating DB."""
        self.path = path
        with closing(sqlite3.connect(path)) as connection, connection:
            _ = connection.execute(
                """CREATE TABLE IF NOT EXISTS config_commands (
                  account_id TEXT NOT NULL, environment TEXT NOT NULL,
                  symbol TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                  command_id TEXT NOT NULL, payload TEXT NOT NULL,
                  digest TEXT NOT NULL, decision TEXT NOT NULL,
                  reason TEXT NOT NULL, accepted_version INTEGER,
                  actor_id TEXT NOT NULL,
                  PRIMARY KEY (account_id, environment, symbol, idempotency_key),
                  UNIQUE (account_id, environment, command_id))"""
            )
            _ = connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS one_accepted_version
                  ON config_commands(account_id, environment, symbol, accepted_version)
                  WHERE accepted_version IS NOT NULL"""
            )

    def receive(self, command: ConfigCommand, actor: Actor, now: datetime) -> Decision:
        """Authorize, deduplicate and compare-and-set the desired revision."""
        settings = command.settings
        scope = (settings.account_id, settings.environment, settings.symbol)
        fingerprint = digest(command)
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            # Never expose a recorded decision to an unauthorized caller.
            if (
                actor.account_id != settings.account_id
                or actor.environment != settings.environment
                or "CONFIG_WRITE" not in actor.permissions
            ):
                return Decision(
                    state="REJECTED", reason="CONFIG_UNAUTHORIZED", digest=fingerprint
                )
            rows = connection.execute(
                """SELECT idempotency_key, command_id, payload, decision, reason, digest
                   FROM config_commands WHERE account_id=? AND environment=?
                   AND symbol=? AND (idempotency_key=? OR command_id=?)""",
                (*scope, command.idempotency_key, str(command.command_id)),
            ).fetchall()
            if rows:
                if len(rows) != 1 or rows[0][:3] != (
                    command.idempotency_key,
                    str(command.command_id),
                    command.model_dump_json(),
                ):
                    raise CommandConflictError("CONFLICT_CONFIG_COMMAND_IDENTITY")
                return Decision(state=rows[0][3], reason=rows[0][4], digest=rows[0][5])
            row = connection.execute(
                """SELECT MAX(accepted_version) FROM config_commands
                   WHERE account_id=? AND environment=? AND symbol=?""",
                scope,
            ).fetchone()
            current = row[0] if row and row[0] is not None else 0
            outcome = decide(command, actor, current_version=current, now=now)
            _ = connection.execute(
                """INSERT INTO config_commands VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *scope,
                    command.idempotency_key,
                    str(command.command_id),
                    command.model_dump_json(),
                    fingerprint,
                    outcome.state,
                    outcome.reason,
                    settings.version if outcome.state == "ACCEPTED" else None,
                    actor.actor_id,
                ),
            )
            return outcome
