"""Resumable bridge from the desired-settings inbox to the local ledger."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from contracts.inbox import ConfigInbox, InboxApplication
from execution.ledger import Ledger
from execution.models import LedgerError


@dataclass(frozen=True, slots=True)
class ConfigApplyResult:
    """Local application state; APPLIED does not mean monitoring is active."""

    command_id: UUID
    state: Literal["NOT_APPLIED", "APPLYING", "APPLIED", "APPLY_BLOCKED"]
    reason: str | None
    applied_version: int | None


class ConfigApplyCoordinator:
    """Coordinate two independent SQLite stores with an explicit recovery state."""

    def __init__(self, inbox: ConfigInbox, ledger: Ledger) -> None:
        """Require distinct desired and execution database paths."""
        if inbox.path.resolve() == ledger.storage.path.resolve():
            raise ValueError("CONFIG_STORES_MUST_BE_SEPARATE")
        self.inbox = inbox
        self.ledger = ledger

    def apply(
        self, command_id: UUID, *, retry_blocked: bool = False
    ) -> ConfigApplyResult:
        """Apply one accepted command, resumable across either DB commit boundary."""
        if not self.ledger.storage.lease.ready:
            raise LedgerError("SESSION_RECONCILIATION_REQUIRED")
        application = self.inbox.begin_apply(command_id, retry_blocked=retry_blocked)
        if application.state != "APPLYING":
            return self._result(application)

        scope = self.ledger.storage.lease.scope
        if (
            application.command.settings.account_id != scope.account_id
            or application.command.settings.environment != scope.environment
        ):
            return self._block(application, "CONFIG_EXECUTION_SCOPE_MISMATCH")

        try:
            applied = self.ledger.apply_inbox_config(
                application.command, command_digest=application.digest
            )
        except LedgerError as error:
            return self._block(application, error.code)

        completed = self.inbox.mark_applied(
            command_id,
            fingerprint=application.digest,
            applied_version=applied.version,
        )
        return self._result(completed)

    def resume_applying(self) -> tuple[ConfigApplyResult, ...]:
        """Recover only APPLYING rows; accepted rows remain intentionally pending."""
        return tuple(
            self.apply(command_id) for command_id in self.inbox.applying_command_ids()
        )

    def resume_pending(self) -> tuple[ConfigApplyResult, ...]:
        """Apply accepted pending commands in accepted-version order after review."""
        if not self.ledger.storage.lease.ready:
            raise LedgerError("SESSION_RECONCILIATION_REQUIRED")
        return tuple(
            self.apply(command_id)
            for command_id in self.inbox.pending_application_ids()
        )

    def _block(self, application: InboxApplication, reason: str) -> ConfigApplyResult:
        blocked = self.inbox.block_apply(application.command.command_id, reason)
        return self._result(blocked)

    @staticmethod
    def _result(application: InboxApplication) -> ConfigApplyResult:
        return ConfigApplyResult(
            command_id=application.command.command_id,
            state=application.state,
            reason=application.reason,
            applied_version=application.applied_version,
        )
