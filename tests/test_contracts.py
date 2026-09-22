"""Shared contract fixture validation tests."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.models import ContractBundle

FIXTURE = Path(__file__).parents[1] / "contracts" / "fixtures" / "step02-contract.json"


def load_fixture() -> dict[str, Any]:
    """Load the exact JSON document consumed by Python and TypeScript tests."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_python_accepts_shared_contract_fixture() -> None:
    bundle = ContractBundle.model_validate(load_fixture())

    assert bundle.instrument.symbol == "005930"
    assert bundle.execution_config.state == "ACCEPTED"
    assert bundle.order.filled_quantity == sum(fill.quantity for fill in bundle.fills)


def test_python_rejects_accepted_config_with_wrong_applied_version() -> None:
    payload = deepcopy(load_fixture())
    payload["execution_config"]["applied_version"] = 1

    with pytest.raises(ValidationError, match="ACCEPTED_VERSION_MISMATCH"):
        ContractBundle.model_validate(payload)


def test_python_rejects_nonhyphenated_uuid_text() -> None:
    payload = deepcopy(load_fixture())
    payload["patterns"][0]["pattern_id"] = "11111111111141118111111111111111"
    payload["execution_config"]["buy_pattern"]["pattern_id"] = (
        "11111111111141118111111111111111"
    )

    with pytest.raises(ValidationError, match="INVALID_UUID_FORMAT"):
        ContractBundle.model_validate(payload)


@pytest.mark.parametrize(
    "invalid_requested_at",
    [
        1_795_478_400,
        "2026-09-22 00:00:00Z",
        "2026-09-22T00:00:00z",
        "2026-09-22T00:00:00+0900",
    ],
)
def test_python_rejects_noncanonical_datetime_inputs(
    invalid_requested_at: object,
) -> None:
    payload = deepcopy(load_fixture())
    payload["execution_config"]["requested_at"] = invalid_requested_at

    with pytest.raises(ValidationError, match="INVALID_DATETIME_FORMAT"):
        ContractBundle.model_validate(payload)


def test_python_rejects_integers_outside_javascript_safe_range() -> None:
    payload = deepcopy(load_fixture())
    payload["order"]["quantity"] = 9_007_199_254_740_992
    payload["order"]["filled_quantity"] = 9_007_199_254_740_992
    payload["order"]["remaining_quantity"] = 0
    payload["order"]["state"] = "FILLED"
    payload["fills"][0]["quantity"] = 9_007_199_254_740_992

    with pytest.raises(ValidationError):
        ContractBundle.model_validate(payload)


def test_python_rejects_datetime_precision_beyond_milliseconds() -> None:
    payload = deepcopy(load_fixture())
    payload["execution_config"]["requested_at"] = "2026-09-22T00:00:00.000001Z"

    with pytest.raises(ValidationError, match="INVALID_DATETIME_FORMAT"):
        ContractBundle.model_validate(payload)


@pytest.mark.parametrize(
    "requested_at",
    [
        "2026-09-22T00:00:00.1Z",
        "2026-09-22T00:00:00.12Z",
        "2026-09-22T00:00:00.123Z",
    ],
)
def test_python_accepts_one_to_three_fractional_second_digits(
    requested_at: str,
) -> None:
    payload = deepcopy(load_fixture())
    payload["execution_config"]["requested_at"] = requested_at

    bundle = ContractBundle.model_validate(payload)

    assert bundle.execution_config.requested_at.microsecond > 0


def test_python_rejects_boolean_schema_version() -> None:
    payload = deepcopy(load_fixture())
    payload["schema_version"] = True

    with pytest.raises(ValidationError):
        ContractBundle.model_validate(payload)


def test_python_accepts_json_numeric_schema_version() -> None:
    payload = deepcopy(load_fixture())
    payload["schema_version"] = 1.0

    bundle = ContractBundle.model_validate(payload)

    assert bundle.schema_version == 1


def test_python_requires_schema_version() -> None:
    payload = deepcopy(load_fixture())
    del payload["schema_version"]

    with pytest.raises(ValidationError):
        ContractBundle.model_validate(payload)


def test_python_rejects_integer_for_boolean_field() -> None:
    payload = deepcopy(load_fixture())
    payload["operation"]["live_trading_enabled"] = 0

    with pytest.raises(ValidationError):
        ContractBundle.model_validate(payload)


def test_python_accepts_integral_json_numbers_for_integer_fields() -> None:
    payload = deepcopy(load_fixture())
    payload["execution_config"]["requested_version"] = 2.0
    payload["execution_config"]["applied_version"] = 2.0
    payload["order"]["quantity"] = 10.0
    payload["order"]["filled_quantity"] = 4.0
    payload["order"]["cancelled_quantity"] = 0.0
    payload["order"]["remaining_quantity"] = 6.0
    payload["fills"][0]["quantity"] = 4.0

    bundle = ContractBundle.model_validate(payload)

    assert bundle.order.quantity == 10
