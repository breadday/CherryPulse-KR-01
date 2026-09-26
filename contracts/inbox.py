"""Durable desired-settings inbox, separate from the trading ledger."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from contracts.settings import (
    ConfigAuthenticator,
    ConfigCommand,
    Decision,
    decide,
    digest,
)


class CommandConflictError(ValueError):
    """The same command identity has been reused with different content."""


class ConfigInboxError(ValueError):
    """The requested settings-application transition is not valid."""


@dataclass(frozen=True, slots=True)
class InboxApplication:
    """An accepted desired command and its independent local-apply status."""

    command: ConfigCommand
    digest: str
    state: Literal["NOT_APPLIED", "APPLYING", "APPLIED", "APPLY_BLOCKED"]
    reason: str | None
    applied_version: int | None


class ConfigInbox:
    """Persist authenticated desired commands without claiming engine application.

    No authenticator is supplied by this repository. The default inbox therefore
    fails closed. A deployment must inject its real trusted ingress adapter.
    """

    def __init__(
        self, path: Path, *, authenticator: ConfigAuthenticator | None = None
    ) -> None:
        """Create an isolated inbox, never opening an operating database."""
        self.path = path
        self._authenticator = authenticator
        with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            _ = connection.execute(
                """CREATE TABLE IF NOT EXISTS config_commands (
                  account_id TEXT NOT NULL, environment TEXT NOT NULL,
                  symbol TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                  command_id TEXT NOT NULL, payload TEXT NOT NULL,
                  digest TEXT NOT NULL, decision TEXT NOT NULL,
                  reason TEXT NOT NULL, accepted_version INTEGER,
                  actor_id TEXT NOT NULL,
                  apply_state TEXT NOT NULL DEFAULT 'NOT_APPLIED',
                  apply_reason TEXT, applied_version INTEGER,
                  PRIMARY KEY (account_id, environment, symbol, idempotency_key),
                  UNIQUE (account_id, environment, command_id))"""
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(config_commands)")
            }
            legacy_acceptance = "apply_state" not in columns
            for name, definition in (
                ("apply_state", "TEXT NOT NULL DEFAULT 'NOT_APPLIED'"),
                ("apply_reason", "TEXT"),
                ("applied_version", "INTEGER"),
            ):
                if name not in columns:
                    _ = connection.execute(
                        f"ALTER TABLE config_commands ADD COLUMN {name} {definition}"
                    )
            if legacy_acceptance:
                # Historical ACCEPTED rows only contain caller-provided Actor claims.
                _ = connection.execute(
                    """UPDATE config_commands SET apply_state='APPLY_BLOCKED',
                       apply_reason='LEGACY_AUTHENTICATION_UNVERIFIED',
                       accepted_version=NULL
                       WHERE decision='ACCEPTED'"""
                )
            _ = connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS one_accepted_version
                  ON config_commands(account_id, environment, symbol, accepted_version)
                  WHERE accepted_version IS NOT NULL"""
            )

    def receive(
        self,
        command: ConfigCommand,
        now: datetime,
        *,
        auth_context: object | None = None,
    ) -> Decision:
        """Authenticate, authorize, deduplicate and persist a desired decision.

        The authentication context is transient and is never stored. A bare
        ``Actor`` claim cannot be supplied by the caller as proof of identity.
        """
        command = ConfigCommand.model_validate_json(command.model_dump_json())
        fingerprint = digest(command)
        if self._authenticator is None:
            return Decision(
                state="REJECTED",
                reason="CONFIG_AUTHENTICATION_UNAVAILABLE",
                digest=fingerprint,
            )
        if auth_context is None:
            return Decision(
                state="REJECTED",
                reason="CONFIG_AUTHENTICATION_EVIDENCE_REQUIRED",
                digest=fingerprint,
            )
        actor = self._authenticator.authenticate(command, auth_context)
        if actor is None:
            return Decision(
                state="REJECTED",
                reason="CONFIG_AUTHENTICATION_FAILED",
                digest=fingerprint,
            )

        settings = command.settings
        scope = (settings.account_id, settings.environment, settings.symbol)
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            # Never expose a recorded decision to an out-of-scope principal.
            if (
                actor.account_id != settings.account_id
                or actor.environment != settings.environment
                or "CONFIG_WRITE" not in actor.permissions
            ):
                return Decision(
                    state="REJECTED",
                    reason="CONFIG_UNAUTHORIZED",
                    digest=fingerprint,
                )
            rows = connection.execute(
                """SELECT symbol, idempotency_key, command_id, payload,
                          decision, reason, digest
                   FROM config_commands WHERE account_id=? AND environment=?
                   AND ((symbol=? AND idempotency_key=?) OR command_id=?)""",
                (*scope, command.idempotency_key, str(command.command_id)),
            ).fetchall()
            if rows:
                if len(rows) != 1 or rows[0][:4] != (
                    settings.symbol,
                    command.idempotency_key,
                    str(command.command_id),
                    command.model_dump_json(),
                ):
                    raise CommandConflictError("CONFLICT_CONFIG_COMMAND_IDENTITY")
                return Decision(state=rows[0][4], reason=rows[0][5], digest=rows[0][6])
            row = connection.execute(
                """SELECT MAX(accepted_version) FROM config_commands
                   WHERE account_id=? AND environment=? AND symbol=?""",
                scope,
            ).fetchone()
            current = row[0] if row and row[0] is not None else 0
            outcome = decide(command, actor, current_version=current, now=now)
            _ = connection.execute(
                """INSERT INTO config_commands (
                    account_id, environment, symbol, idempotency_key, command_id,
                    payload, digest, decision, reason, accepted_version, actor_id,
                    apply_state, apply_reason, applied_version
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'NOT_APPLIED',NULL,NULL)""",
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

    def begin_apply(
        self, command_id: UUID, *, retry_blocked: bool = False
    ) -> InboxApplication:
        """Durably enter APPLYING before the independent local-ledger write.

        APPLYING is deliberately resumable after process restart. Retrying a
        terminal apply conflict requires an explicit caller decision.
        """
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT payload,digest,decision,apply_state,apply_reason,
                          applied_version FROM config_commands
                   WHERE command_id=?""",
                (str(command_id),),
            ).fetchone()
            if row is None:
                raise ConfigInboxError("CONFIG_COMMAND_NOT_FOUND")
            payload, fingerprint, decision, state, reason, applied_version = row
            if decision != "ACCEPTED":
                raise ConfigInboxError("CONFIG_COMMAND_NOT_ACCEPTED")
            if state == "APPLY_BLOCKED" and (
                not retry_blocked or reason == "LEGACY_AUTHENTICATION_UNVERIFIED"
            ):
                return InboxApplication(
                    ConfigCommand.model_validate_json(payload),
                    fingerprint,
                    state,
                    reason,
                    applied_version,
                )
            if state not in ("NOT_APPLIED", "APPLYING", "APPLIED", "APPLY_BLOCKED"):
                raise ConfigInboxError("CONFIG_APPLY_STATE_INVALID")
            if state in ("NOT_APPLIED", "APPLY_BLOCKED"):
                _ = connection.execute(
                    """UPDATE config_commands SET apply_state='APPLYING',
                       apply_reason=NULL WHERE command_id=?""",
                    (str(command_id),),
                )
                state = "APPLYING"
                reason = None
            return InboxApplication(
                ConfigCommand.model_validate_json(payload),
                fingerprint,
                state,
                reason,
                applied_version,
            )

    def applying_command_ids(self) -> tuple[UUID, ...]:
        """List in-flight cross-database transitions for explicit restart recovery."""
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            rows = connection.execute(
                """SELECT command_id FROM config_commands
                   WHERE decision='ACCEPTED' AND apply_state='APPLYING'
                   ORDER BY rowid"""
            ).fetchall()
        return tuple(UUID(row[0]) for row in rows)

    def pending_application_ids(self) -> tuple[UUID, ...]:
        """List accepted desired commands not yet locally applied, oldest first."""
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            rows = connection.execute(
                """SELECT command_id FROM config_commands
                   WHERE decision='ACCEPTED'
                     AND apply_state IN ('NOT_APPLIED','APPLYING')
                   ORDER BY accepted_version, rowid"""
            ).fetchall()
        return tuple(UUID(row[0]) for row in rows)

    def block_apply(self, command_id: UUID, reason: str) -> InboxApplication:
        """Record a failed local application without changing accepted desired data."""
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT payload,digest,decision,apply_state,apply_reason,
                          applied_version FROM config_commands
                   WHERE command_id=?""",
                (str(command_id),),
            ).fetchone()
            if row is None:
                raise ConfigInboxError("CONFIG_COMMAND_NOT_FOUND")
            payload, fingerprint, decision, state, old_reason, applied_version = row
            if decision != "ACCEPTED":
                raise ConfigInboxError("CONFIG_COMMAND_NOT_ACCEPTED")
            if state == "APPLIED":
                raise ConfigInboxError("CONFIG_ALREADY_APPLIED")
            if state == "APPLY_BLOCKED" and old_reason == reason:
                pass
            elif state == "APPLYING":
                _ = connection.execute(
                    """UPDATE config_commands SET apply_state='APPLY_BLOCKED',
                       apply_reason=? WHERE command_id=?""",
                    (reason, str(command_id)),
                )
            else:
                raise ConfigInboxError("CONFIG_APPLY_NOT_IN_PROGRESS")
            return InboxApplication(
                ConfigCommand.model_validate_json(payload),
                fingerprint,
                "APPLY_BLOCKED",
                reason,
                applied_version,
            )

    def mark_applied(
        self, command_id: UUID, *, fingerprint: str, applied_version: int
    ) -> InboxApplication:
        """Acknowledge APPLIED only after the local ledger returned durable proof."""
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT payload,digest,decision,apply_state,apply_reason,
                          applied_version FROM config_commands
                   WHERE command_id=?""",
                (str(command_id),),
            ).fetchone()
            if row is None:
                raise ConfigInboxError("CONFIG_COMMAND_NOT_FOUND")
            payload, stored_digest, decision, state, reason, stored_version = row
            if decision != "ACCEPTED":
                raise ConfigInboxError("CONFIG_COMMAND_NOT_ACCEPTED")
            if stored_digest != fingerprint:
                raise CommandConflictError("CONFLICT_CONFIG_COMMAND_IDENTITY")
            if (
                applied_version
                != ConfigCommand.model_validate_json(payload).settings.version
            ):
                raise CommandConflictError("CONFLICT_CONFIG_APPLIED_VERSION")
            if state == "APPLIED":
                if stored_version != applied_version:
                    raise CommandConflictError("CONFLICT_CONFIG_APPLIED_VERSION")
            elif state == "APPLYING":
                _ = connection.execute(
                    """UPDATE config_commands SET apply_state='APPLIED',
                       apply_reason=NULL, applied_version=? WHERE command_id=?""",
                    (applied_version, str(command_id)),
                )
                reason = None
            else:
                raise ConfigInboxError("CONFIG_APPLY_NOT_IN_PROGRESS")
            return InboxApplication(
                ConfigCommand.model_validate_json(payload),
                stored_digest,
                "APPLIED",
                reason,
                applied_version,
            )

    def application(self, command_id: UUID) -> InboxApplication:
        """Read desired/application state without implying that monitoring is active."""
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            row = connection.execute(
                """SELECT payload,digest,decision,apply_state,apply_reason,
                          applied_version FROM config_commands
                   WHERE command_id=?""",
                (str(command_id),),
            ).fetchone()
        if row is None:
            raise ConfigInboxError("CONFIG_COMMAND_NOT_FOUND")
        payload, fingerprint, decision, state, reason, applied_version = row
        if decision != "ACCEPTED":
            raise ConfigInboxError("CONFIG_COMMAND_NOT_ACCEPTED")
        return InboxApplication(
            ConfigCommand.model_validate_json(payload),
            fingerprint,
            state,
            reason,
            applied_version,
        )
