import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Final
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from execution.ledger import Ledger
from execution.models import LedgerError, Scope
from execution.ownership import account_lock
from execution.virtual import VirtualDispatcher

HOLDER: Final = """
import os
import sys
from pathlib import Path
from execution.ledger import Ledger
from execution.models import New, Scope
from execution.ownership import account_lock
from execution.virtual import VirtualDispatcher
scope = Scope.model_validate_json(sys.argv[2])
root = Path(sys.argv[1])
with account_lock(root / 'locks', scope) as lease:
    book = Ledger(root / 'ledger.sqlite3', lease)
    book.approve_virtual_reconciliation(0)
    request = book.submit(New(key='crash-intent', symbol='005930', side='BUY',
        qty=100, config_version=1, order_type='MARKET', session='REGULAR',
        validity='DAY')).request
    VirtualDispatcher(book).send(request.request_id)
    print('READY', flush=True)
    sys.stdin.readline()
    os._exit(23)
"""
CONTENDER: Final = """
import sys
from pathlib import Path
from execution.ledger import Ledger
from execution.models import LedgerError, Scope
from execution.ownership import account_lock
try:
    with account_lock(Path(sys.argv[1]) / 'locks',
                      Scope.model_validate_json(sys.argv[2])) as lease:
        Ledger(Path(sys.argv[1]) / 'ledger.sqlite3', lease)
except LedgerError as error:
    print(error.code)
else:
    raise SystemExit(2)
"""


def test_real_process_contention_and_crash_recovery(tmp_path: Path) -> None:
    # Given: a real child process holds a lease with a SENT request in SQLite.
    scope = Scope(
        account_id="PROCESS_TEST", environment="PAPER", execution_scope=uuid4()
    )
    cwd = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-u",
        "-c",
        HOLDER,
        str(tmp_path),
        scope.model_dump_json(),
    ]
    with subprocess.Popen[str](
        command,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as holder:
        assert holder.stdout is not None
        try:
            ready = TypeAdapter(str).validate_python(holder.stdout.readline())
            assert ready.strip() == "READY"
            before = sha256((tmp_path / "ledger.sqlite3").read_bytes()).digest()
            # When: a second process competes, then the owner exits without cleanup.
            contender = subprocess.run(  # noqa: S603 - fixed synthetic test command.
                [
                    sys.executable,
                    "-c",
                    CONTENDER,
                    str(tmp_path),
                    scope.model_dump_json(),
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            assert contender.returncode == 0, contender.stderr
            assert contender.stdout.strip() == "ACCOUNT_LOCK_BUSY_READ_ONLY"
            assert sha256((tmp_path / "ledger.sqlite3").read_bytes()).digest() == before
        finally:
            _ = holder.communicate("crash\n", timeout=10)
        assert holder.returncode == 23
    # Then: OS exclusion is released, but the fresh session cannot resume sends.
    with account_lock(tmp_path / "locks", scope) as recovered:
        book = Ledger(tmp_path / "ledger.sqlite3", recovered)
        dispatcher = VirtualDispatcher(book)
        pending = dispatcher.recover()
        assert len(pending) == 1
        assert not recovered.ready
        with pytest.raises(LedgerError, match="SESSION_RECONCILIATION_REQUIRED"):
            book.approve_virtual_reconciliation(book.snapshot().revision)
        assert not dispatcher.send(pending[0])
        assert dispatcher.calls == []
        assert book.transport(pending[0]) == "RECONCILING"


def test_environment_is_part_of_account_lock_namespace(tmp_path: Path) -> None:
    # Given
    execution = uuid4()
    paper = Scope(account_id="ENV_TEST", environment="PAPER", execution_scope=execution)
    live = Scope(account_id="ENV_TEST", environment="LIVE", execution_scope=execution)
    # When / Then: both adapters remain virtual; no external connection exists.
    with account_lock(tmp_path, paper) as first, account_lock(tmp_path, live) as second:
        assert first.scope.environment != second.scope.environment
