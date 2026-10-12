"""Pure virtual buy evaluation for the confirmed Q12 first version; no orders."""

from dataclasses import dataclass
from datetime import datetime, timedelta
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


def _expiry_block_reason(
    expires_at: datetime | None, timing: ObserveAt, session_end: datetime
) -> str | None:
    """Require an explicit same-session expiry on every virtual buy."""
    if expires_at is None or expires_at.utcoffset() is None:
        return "EXPIRY_REQUIRED"
    if session_end.utcoffset() is None:
        return "EXPIRY_REQUIRED"
    if expires_at <= timing.now:
        return "COMMAND_EXPIRED"
    if expires_at > session_end:
        return "EXPIRY_BEYOND_SESSION"
    return None


def _standing_block_reason(managed_qty: int, filled_today_qty: int) -> str | None:
    """Block buys against held shares or an earlier completed buy cycle."""
    if managed_qty > 0:
        return "HOLDING_BLOCKS_BUY"
    if filled_today_qty > 0:
        return "DAY_REENTRY_BLOCKED"
    return None


def _market_block_reason(
    *, quote: Quote, timing: ObserveAt, target: Decimal
) -> str | None:
    """Compare one fresh quote against the validated target price."""
    age = timing.now - quote.received_at
    if age < timedelta(0) or age > timedelta(seconds=timing.max_quote_age_seconds):
        return "QUOTE_NOT_FRESH"
    if quote.price > target:
        return "PRICE_ABOVE_TARGET"
    return None


def evaluate_virtual_buy(  # noqa: PLR0913 - eight explicit keyword-only contract inputs.
    *,
    symbol: str,
    target_price: str,
    quote: Quote | None,
    timing: ObserveAt,
    managed_qty: int,
    filled_today_qty: int,
    expires_at: datetime | None,
    session_end: datetime,
) -> BuyDecision:
    """Decide one fixed-share virtual buy under the Q12 first-version contract.

    Holdings short-circuit before any quote inspection: with managed shares the
    buy condition is not evaluated (Q12 4.2/6.2). A completed buy cycle earlier
    the same day blocks re-entry even back at zero holdings (Q12 4.1); the
    day boundary reset stays with the caller-side session layer. Every virtual
    buy carries an explicit expiry inside the session (Q12 2.2/2.3).
    """
    blocked = _target_block_reason(target_price)
    if blocked is not None:
        return BuyDecision(status="BUY_BLOCKED", reason=blocked)
    expired = _expiry_block_reason(expires_at, timing, session_end)
    if expired is not None:
        return BuyDecision(status="BUY_BLOCKED", reason=expired)
    standing = _standing_block_reason(managed_qty, filled_today_qty)
    if standing is not None:
        return BuyDecision(status="BUY_BLOCKED", reason=standing)
    if quote is None or quote.symbol != symbol:
        return BuyDecision(status="BUY_BLOCKED", reason="QUOTE_MISSING_OR_WRONG_SYMBOL")
    market = _market_block_reason(
        quote=quote, timing=timing, target=Decimal(target_price)
    )
    if market is not None:
        return BuyDecision(status="BUY_BLOCKED", reason=market)
    return BuyDecision(
        status="BUY_CANDIDATE", reason="TARGET_AND_FRESHNESS_OK", qty=BUY_QTY
    )
