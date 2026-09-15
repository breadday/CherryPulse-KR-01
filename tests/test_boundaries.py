from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from execution.facts import Fill
from execution.ledger import Ledger
from execution.models import Allocation, LedgerError, Scope
from execution.ownership import account_lock
from tests.conftest import Scenario


@pytest.mark.parametrize("qty", ["true", "1.0", '"1"', "0", "-1", "null"])
def test_invalid_quantity_when_json_is_not_positive_integer(
    scenario: Scenario, qty: str
) -> None:
    # Given
    payload = (
        '{"kind":"NEW","key":"k","symbol":"005930","side":"BUY","config_version":1,"qty":'
        + qty
        + ',"order_type":"MARKET","session":"REGULAR","validity":"DAY"}'
    )
    # When / Then
    with pytest.raises(ValidationError):
        _ = scenario.book.submit_json(payload)
    assert scenario.book.snapshot().requests == ()


@pytest.mark.parametrize("price", ['"1e4"', '"10,000"', "10000.0", "null", '"0"'])
def test_invalid_limit_price_when_decimal_contract_is_violated(
    scenario: Scenario, price: str
) -> None:
    # Given
    payload = (
        '{"kind":"NEW","key":"k","symbol":"005930","side":"BUY","config_version":1,"qty":1,"order_type":"LIMIT","session":"REGULAR","validity":"DAY","price":'
        + price
        + "}"
    )
    # When / Then
    with pytest.raises(ValidationError):
        _ = scenario.book.submit_json(payload)
    assert scenario.book.snapshot().requests == ()


def test_same_request_when_price_uses_equivalent_decimal_spelling(
    scenario: Scenario,
) -> None:
    # Given
    payload = (
        '{"kind":"NEW","key":"k","symbol":"005930","side":"BUY",'
        '"config_version":1,"qty":1,"order_type":"LIMIT","session":"REGULAR",'
        '"validity":"DAY","price":"0010000.00"}'
    )
    first = scenario.book.submit_json(payload)
    # When
    repeated = scenario.book.submit_json(payload.replace("0010000.00", "10000"))
    # Then
    assert repeated.request == first.request
    assert not repeated.created


def test_event_conflict_when_stable_identity_has_different_content(
    scenario: Scenario,
) -> None:
    # Given
    buy = scenario.new("BUY", 100)
    first = scenario.fill(buy, (20, 80))
    conflicting = Fill(
        event_id=first.event_id,
        order_id=buy.order_id,
        qty=30,
        remaining=70,
        evidence_version=1,
    )
    # When
    with pytest.raises(LedgerError, match="CONFLICT_EVENT_ID_MISMATCH"):
        _ = scenario.book.ingest(conflicting)
    # Then
    assert scenario.book.portfolio("005930").managed == 20


def test_scope_isolation_when_keys_and_symbols_match(tmp_path: Path) -> None:
    # Given
    path = tmp_path / "scopes.sqlite3"
    scope_a = Scope(account_id="DEMO_A", environment="PAPER", execution_scope=uuid4())
    scope_b = Scope(account_id="DEMO_B", environment="PAPER", execution_scope=uuid4())
    with (
        account_lock(tmp_path / "locks", scope_a) as lease_a,
        account_lock(tmp_path / "locks", scope_b) as lease_b,
    ):
        first = Ledger(path, lease_a)
        second = Ledger(path, lease_b)
        first.approve_virtual_reconciliation(0)
        second.approve_virtual_reconciliation(0)
        first.allocate(Allocation(symbol="005930", qty=100))
        payload = (
            '{"kind":"NEW","key":"k","symbol":"005930","side":"BUY",'
            '"config_version":1,"qty":1,"order_type":"MARKET",'
            '"session":"REGULAR","validity":"DAY"}'
        )
        # When
        one = first.submit_json(payload)
        two = second.submit_json(payload)
        # Then
        assert one.request.request_id != two.request.request_id
        assert second.portfolio("005930").managed == 0


def test_explicit_null_when_amend_price_should_be_retained(scenario: Scenario) -> None:
    # Given
    scenario.allocate(100)
    sell = scenario.new("SELL", 100)
    payload = (
        '{"kind":"AMEND","key":"a","symbol":"005930","side":"SELL","config_version":1,"target":"'
        + str(sell.order_id)
        + '","link_version":1,"qty_delta":-20,"price":null}'
    )
    # When / Then
    with pytest.raises(ValidationError):
        _ = scenario.book.submit_json(payload)
    assert scenario.book.portfolio("005930").reserved == 100
