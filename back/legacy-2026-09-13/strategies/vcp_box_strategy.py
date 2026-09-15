from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime

from core.models import OrderType, Signal, Side
from .base_strategy import BaseStrategy


class VcpBoxStrategy(BaseStrategy):
    strategy_name = "vcp_box"

    def __init__(self, config=None):
        super().__init__(config=config)
        self.default_qty = max(1, int(self.config.get("default_order_qty", 1) or 1))
        self.history_size = max(20, int(self.config.get("vcp_box_history_size", 80) or 80))
        self.min_history = max(10, int(self.config.get("vcp_box_min_history", 35) or 35))
        self.box_lookback = max(10, int(self.config.get("vcp_box_lookback", 24) or 24))
        self.early_lookback = max(10, int(self.config.get("vcp_box_early_lookback", 24) or 24))
        self.max_box_width_pct = float(self.config.get("vcp_box_max_box_width_pct", 2.8) or 2.8)
        self.min_prior_width_pct = float(self.config.get("vcp_box_min_prior_width_pct", 1.2) or 1.2)
        self.max_contraction_ratio = float(self.config.get("vcp_box_max_contraction_ratio", 0.75) or 0.75)
        self.breakout_buffer_pct = float(self.config.get("vcp_box_breakout_buffer_pct", 0.05) or 0.05)
        self.min_trade_strength = float(self.config.get("vcp_box_min_trade_strength", 80.0) or 80.0)
        self.min_volume_ratio = float(self.config.get("vcp_box_signal_min_volume_ratio", 1.1) or 1.1)
        self.max_price_change_pct = float(self.config.get("vcp_box_signal_max_price_change_pct", 12.0) or 12.0)
        self.min_price_change_pct = float(self.config.get("vcp_box_signal_min_price_change_pct", 0.5) or 0.5)
        self.cooldown_sec = max(0, int(self.config.get("vcp_box_entry_cooldown_sec", 600) or 600))
        self.price_history = defaultdict(lambda: deque(maxlen=self.history_size))
        self.last_entry_at = {}

    def _append_price(self, symbol: str, price: float):
        if price > 0:
            self.price_history[symbol].append(float(price))

    def _range_pct(self, prices) -> float:
        if not prices:
            return 0.0
        low = min(prices)
        high = max(prices)
        if low <= 0:
            return 0.0
        return (high - low) / low * 100.0

    def _cooldown_active(self, symbol: str, ts: datetime) -> bool:
        last_ts = self.last_entry_at.get(symbol)
        if not isinstance(last_ts, datetime) or self.cooldown_sec <= 0:
            return False
        return (ts - last_ts).total_seconds() < self.cooldown_sec

    def generate_signal(self, tick, portfolio=None):
        self.last_reject_reason = ""

        symbol = str(getattr(tick, "symbol", "")).strip()
        price = float(getattr(tick, "price", 0.0) or 0.0)
        ts = getattr(tick, "ts", datetime.now())
        if not isinstance(ts, datetime):
            ts = datetime.now()

        if not symbol:
            self.last_reject_reason = "symbol empty"
            return None
        if price <= 0:
            self.last_reject_reason = "invalid price"
            return None

        self._append_price(symbol, price)

        if portfolio is not None and hasattr(portfolio, "has_position") and portfolio.has_position(symbol):
            self.last_reject_reason = "already has position"
            return None
        if self._cooldown_active(symbol, ts):
            self.last_reject_reason = "entry_cooldown"
            return None

        history = list(self.price_history[symbol])
        if len(history) < self.min_history:
            self.last_reject_reason = f"history<{self.min_history}"
            return None

        current_box = history[-self.box_lookback:]
        prior_box = history[-(self.box_lookback + self.early_lookback):-self.box_lookback]
        if len(current_box) < self.box_lookback or len(prior_box) < self.early_lookback:
            self.last_reject_reason = "box_history_short"
            return None

        box_high_before_tick = max(current_box[:-1]) if len(current_box) > 1 else max(current_box)
        box_low = min(current_box)
        current_width_pct = self._range_pct(current_box)
        prior_width_pct = self._range_pct(prior_box)
        trade_strength = float(getattr(tick, "trade_strength", 0.0) or 0.0)
        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)

        if prior_width_pct < self.min_prior_width_pct:
            self.last_reject_reason = f"prior_width<{self.min_prior_width_pct}"
            return None
        if current_width_pct > self.max_box_width_pct:
            self.last_reject_reason = f"box_width>{self.max_box_width_pct}"
            return None
        if current_width_pct > prior_width_pct * self.max_contraction_ratio:
            self.last_reject_reason = f"not_contracted {current_width_pct:.2f}>{prior_width_pct * self.max_contraction_ratio:.2f}"
            return None

        breakout_price = box_high_before_tick * (1.0 + self.breakout_buffer_pct / 100.0)
        if price < breakout_price:
            self.last_reject_reason = f"below_box_breakout {price:.0f}<{breakout_price:.0f}"
            return None
        if price_change_pct < self.min_price_change_pct:
            self.last_reject_reason = f"chg<{self.min_price_change_pct}"
            return None
        if price_change_pct > self.max_price_change_pct:
            self.last_reject_reason = f"chg>{self.max_price_change_pct}"
            return None
        if volume_ratio < self.min_volume_ratio:
            self.last_reject_reason = f"vr<{self.min_volume_ratio}"
            return None
        if trade_strength < self.min_trade_strength:
            self.last_reject_reason = f"strength<{self.min_trade_strength}"
            return None

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=self.default_qty,
            reason=(
                "vcp_box_breakout"
                f" | box_high={box_high_before_tick:.0f}"
                f" | box_low={box_low:.0f}"
                f" | width={current_width_pct:.2f}"
                f" | prior_width={prior_width_pct:.2f}"
                f" | chg={price_change_pct:.2f}"
                f" | vr={volume_ratio:.2f}"
                f" | strength={trade_strength:.1f}"
            ),
            price=price,
            order_type=OrderType.MARKET,
            ts=ts,
        )

    def mark_entry(self, symbol: str, ts):
        if not isinstance(ts, datetime):
            ts = datetime.now()
        self.last_entry_at[str(symbol).strip()] = ts
