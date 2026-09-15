"""Windows account lock and session ownership boundary."""

import errno
import msvcrt
import os
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Final

from typing_extensions import Self

from execution.models import LedgerError, Scope


class AccountLease:
    """Mutable session gate; a mutex prevents release during an active operation."""

    def __init__(self, scope: Scope) -> None:
        """Create an inactive lease; only acquire can establish ownership."""
        self.scope: Scope = scope
        self._mutex: RLock = RLock()
        self._pid: int = os.getpid()
        self._held: bool = False
        self._ready: bool = False
        self._database: Path | None = None

    @classmethod
    @contextmanager
    def acquire(cls, directory: Path, scope: Scope) -> Generator[Self, None, None]:
        """Acquire account/environment exclusion before any ledger connection."""
        namespace = scope.model_dump_json(exclude={"execution_scope"})
        path = directory / (sha256(namespace.encode()).hexdigest() + ".lock")
        with ExitStack() as resources:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                file = resources.enter_context(path.open("a+b"))
                _ = file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise LedgerError("ACCOUNT_LOCK_BUSY_READ_ONLY") from error
                raise LedgerError("ACCOUNT_LOCK_UNAVAILABLE_READ_ONLY") from error
            lease = cls(scope)
            lease._held = True
            try:
                yield lease
            finally:
                lease.retire()

    @contextmanager
    def operation(self) -> Generator[None, None, None]:
        """Keep the account lease alive until the guarded operation finishes."""
        with self._mutex:
            if not self._held or os.getpid() != self._pid:
                raise LedgerError("ACCOUNT_LOCK_NOT_OWNED")
            yield

    @property
    def ready(self) -> bool:
        """Report readiness only for the process still owning this lease."""
        with self._mutex:
            return self._held and self._ready and os.getpid() == self._pid

    def bind_database(self, path: Path) -> None:
        """Prevent an approved session from switching its underlying order journal."""
        with self.operation():
            resolved = path.resolve()
            if self._database is not None and self._database != resolved:
                raise LedgerError("ACCOUNT_LEDGER_ALREADY_BOUND")
            self._database = resolved

    def require_ready(self) -> None:
        """Reject mutation or dispatch until local virtual recovery is approved."""
        with self.operation():
            if not self._ready:
                raise LedgerError("SESSION_RECONCILIATION_REQUIRED")

    def approve_virtual_review(self) -> None:
        """Open the simulator gate after Ledger verifies its current journal review."""
        with self.operation():
            self._ready = True

    def retire(self) -> None:
        """Wait for in-flight operations, then invalidate every escaped reference."""
        with self._mutex:
            self._held = False
            self._ready = False


account_lock: Final = AccountLease.acquire
