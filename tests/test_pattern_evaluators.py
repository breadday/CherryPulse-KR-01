"""Failing RED tests → GREEN for STEP 04 pattern condition evaluation."""

import sys
from types import ModuleType

import pytest

if sys.platform != "win32":
    msvcrt = ModuleType("msvcrt")
    msvcrt.LK_NBLCK = 1  # type: ignore[attr-defined]
    msvcrt.locking = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    sys.modules.setdefault("msvcrt", msvcrt)

from patterns.evaluation import evaluate_average_price_stop, evaluate_price_threshold


def test_price_threshold_triggers_on_greater_or_equal():
    """PRICE_THRESHOLD/GTE should fire only when observed >= threshold."""
    assert evaluate_price_threshold("12000", "GTE", "11500")
    assert not evaluate_price_threshold("11500", "GTE", "12000")


def test_price_threshold_triggers_on_less_or_equal_for_sell_trigger():
    """PRICE_THRESHOLD/LTE fires when observed <= threshold (inclusive)."""
    assert evaluate_price_threshold("9000", "LTE", "9000")
    assert not evaluate_price_threshold("9500", "LTE", "9000")


def test_average_price_stop_computation_in_sell_trigger():
    """AVERAGE_PRICE_PERCENT should compute the stop target price."""
    assert evaluate_average_price_stop("10000", "-5", "9500")
    assert not evaluate_average_price_stop("10000", "-5", "9999")


def test_average_price_percentage_range_is_strictly_between_zero_and_minus_100():
    """-0 and -100 percent limits should be rejected."""
    with pytest.raises(ValueError, match="PATTERN_PERCENT_OUT_OF_RANGE"):
        evaluate_average_price_stop("10000", "0", "9500")
    with pytest.raises(ValueError, match="PATTERN_PERCENT_OUT_OF_RANGE"):
        evaluate_average_price_stop("10000", "-100", "9500")


def test_pattern_values_reject_exponent_and_float_spellings():
    """Pattern inputs must match the shared plain-decimal contract."""
    with pytest.raises(ValueError, match="PATTERN_INVALID_DECIMAL"):
        evaluate_price_threshold("1e4", "GTE", "10000")
    with pytest.raises(ValueError, match="PATTERN_INVALID_DECIMAL"):
        evaluate_price_threshold("10,000", "GTE", "10000")


def test_average_price_stop_preserves_high_precision_threshold_comparison():
    """Large contract-valid decimals must not round at the default context."""
    assert evaluate_average_price_stop(
        "12345678901234567890123456789",
        "-0.01",
        "12344444333344444433334444443.3211",
    )
