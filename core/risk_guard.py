"""Strategy-independent position stop protection."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RiskPosition:
    symbol: str
    price: object
    avg_price: object
    qty: object
    stop_loss_pct: object
    position_key: str = ""


@dataclass(frozen=True)
class RiskDecision:
    triggered: bool
    reason: str
    symbol: str
    qty: int = 0
    pnl_pct: float = 0.0
    event_type: str = ""


class RiskGuard:
    def __init__(self, store=None, logger=None):
        self.store = store
        self.logger = logger

    def check_stop(self, position: RiskPosition) -> RiskDecision:
        values = (position.price, position.avg_price, position.qty, position.stop_loss_pct)
        try:
            if any(isinstance(v, bool) for v in values):
                raise ValueError
            price, avg, qty, stop = (float(v) for v in values)
            if not all(math.isfinite(v) for v in (price, avg, qty, stop)) or price <= 0 or avg <= 0 or qty <= 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            return RiskDecision(False, "INVALID_INPUT", str(position.symbol), 0, 0.0, "INVALID_INPUT")
        pnl = (price - avg) / avg
        if pnl <= stop:
            return RiskDecision(True, f"stop_loss {pnl:.2%}", str(position.symbol), int(qty), pnl, "STOP_DETECTED")
        return RiskDecision(False, "NO_STOP", str(position.symbol), int(qty), pnl, "")

    def should_submit(self, symbol, position_key, open_sell_exists, state=None):
        if open_sell_exists:
            return False
        if isinstance(state, dict) and state.get("state") in {
            "STOP_DETECTED", "SELL_SUBMITTING", "SELL_WORKING", "SELL_PARTIAL",
            "CANCEL_REQUESTED", "RETRY_PENDING", "SELL_FILLED", "CLOSED",
            "MANUAL_INTERVENTION_REQUIRED",
        }:
            return False
        if self.store is not None:
            try:
                if self.store.get_risk_event_by_idempotency_key(f"{symbol}:{position_key}:stop"):
                    return False
            except Exception:
                return False
        return True

    def restore_pending(self):
        if self.store is None:
            return []
        # A storage outage must not look like a clean restart.
        return self.store.get_open_risk_events()
