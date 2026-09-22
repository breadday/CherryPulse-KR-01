"""Pattern condition evaluation — STEP 04 basic evaluators.

This module provides pure evaluation of condition expressions. It does NOT:
- submit any orders
- know about broker APIs
- decide whether the pattern should be used — only evaluates formulas

All inputs must come from shared API contract boundary models (or strictly
validated strings) to avoid accidental float comparisons or invalid input.
"""

from decimal import Decimal, localcontext
import re


_DECIMAL_TEXT = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")


def canonical_price(value: str) -> str:
    """Return canonical plain-decimal string for a price input."""
    if not isinstance(value, str) or _DECIMAL_TEXT.fullmatch(value) is None:
        raise ValueError("PATTERN_INVALID_DECIMAL")
    normalized = format(Decimal(value), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return "0" if normalized in {"-0", ""} else normalized


def evaluate_price_threshold(observed_price: str, comparison: str, threshold_price: str) -> bool:
    """Evaluate one absolute price trigger.

    comparison is "GTE" (observed >= threshold) or "LTE" (observed <= threshold);
    anything else raises ValueError with code ``PATTERN_UNKNOWN_COMPARISON``.
    All financial values are Decimal — no binary float comparison.
    """
    observed = Decimal(canonical_price(observed_price))
    threshold = Decimal(canonical_price(threshold_price))
    if observed <= 0 or threshold <= 0:
        raise ValueError("PATTERN_PRICE_MUST_BE_POSITIVE")
    match comparison:
        case "GTE":
            return observed >= threshold
        case "LTE":
            return observed <= threshold
        case _:
            raise ValueError("PATTERN_UNKNOWN_COMPARISON")


def evaluate_average_price_stop(average_price: str, percent: str, current_price: str) -> bool:
    """Evaluate percent-relative stop vs average fill price.

    percent is negative and strictly between 0 and −100. If current price is
    at or below the threshold derived from the average price, the stop condition
    is true.
    """
    avg = Decimal(canonical_price(average_price))
    pct = Decimal(canonical_price(percent))
    current = Decimal(canonical_price(current_price))
    if avg <= 0 or current <= 0:
        raise ValueError("PATTERN_PRICE_MUST_BE_POSITIVE")
    if not Decimal(-100) < pct < 0:
        raise ValueError("PATTERN_PERCENT_OUT_OF_RANGE")
    precision = sum(len(value.as_tuple().digits) for value in (avg, pct, current)) + 10
    with localcontext() as context:
        context.prec = precision
        threshold = avg * (Decimal(1) + pct / Decimal(100))
    return current <= threshold
