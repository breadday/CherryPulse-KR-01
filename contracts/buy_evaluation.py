"""Pure virtual buy evaluation for the confirmed Q12 first version; no orders."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from contracts.stop_evaluation import ObserveAt, Quote

MAX_BUY_TARGET_PRICE = Decimal(100000)
BUY_QTY = 1


@dataclass(frozen=True, slots=True)
class BuyDecision:
    """A buy evaluation outcome; never an order or a send permission."""

    status: Literal["BUY_CANDIDATE", "BUY_BLOCKED"]
    reason: str
    qty: int = 0


def _target_block_reason(target_price: str) -> str | None:
    """Reject an unusable or over-budget target before any market inspection."""
    try:
        target = Decimal(target_price)
    except (InvalidOperation, ValueError):
        return "TARGET_PRICE_INVALID"
    if not target.is_finite() or target <= 0:
        return "TARGET_PRICE_INVALID"
    if target > MAX_BUY_TARGET_PRICE:
        return "TARGET_OVER_BUDGET"
    return None


def evaluate_virtual_buy(
    *,
    symbol: str,
    target_price: str,
    quote: Quote | None,
    timing: ObserveAt,
    managed_qty: int,
) -> BuyDecision:
    """Decide one fixed-share virtual buy under the Q12 first-version contract.

    Holdings short-circuit before any quote inspection: with managed shares the
    buy condition is not evaluated (Q12 4.2/6.2). Same-day re-entry after a
    full exit back to zero holdings is not tracked here and stays blocked by
    caller-side command review.
    """
    blocked = _target_block_reason(target_price)
    if blocked is not None:
        return BuyDecision(status="BUY_BLOCKED", reason=blocked)
    if managed_qty > 0:
        return BuyDecision(status="BUY_BLOCKED", reason="HOLDING_BLOCKS_BUY")
    if quote is None or quote.symbol != symbol:
        return BuyDecision(status="BUY_BLOCKED", reason="QUOTE_MISSING_OR_WRONG_SYMBOL")
    age = timing.now - quote.received_at
    if age < timedelta(0) or age > timedelta(seconds=timing.max_quote_age_seconds):
        return BuyDecision(status="BUY_BLOCKED", reason="QUOTE_NOT_FRESH")
    target = Decimal(target_price)
    if quote.price > target:
        return BuyDecision(status="BUY_BLOCKED", reason="PRICE_ABOVE_TARGET")
    return BuyDecision(
        status="BUY_CANDIDATE", reason="TARGET_AND_FRESHNESS_OK", qty=BUY_QTY
    )
