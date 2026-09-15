from pathlib import Path

from execution.ledger import Ledger
from execution.models import Allocation, New
from execution.ownership import AccountLease


def test_reservation_survives_restart_when_sell_is_submitted(
    tmp_path: Path, lease: AccountLease
) -> None:
    # Given: explicitly allocated holdings and explicit virtual order conditions.
    path = tmp_path / "ledger.sqlite3"
    book = Ledger(path, lease)
    book.approve_virtual_reconciliation(0)
    book.allocate(Allocation(symbol="005930", qty=100))
    command = New(
        key="sell-1",
        symbol="005930",
        side="SELL",
        config_version=1,
        qty=100,
        order_type="LIMIT",
        price="10000.00",
        session="REGULAR",
        validity="DAY",
    )
    # When: the intention is persisted and the ledger is reopened.
    result = book.submit(command)
    restored = Ledger(path, lease)
    # Then: submission reserves shares without changing the actual holding.
    assert result.created
    assert restored.portfolio("005930").managed == 100
    assert restored.portfolio("005930").reserved == 100
