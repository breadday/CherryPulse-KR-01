from __future__ import annotations

from datetime import datetime
from typing import Any

from core.models import OrderType, Signal, Side
from .base_strategy import BaseStrategy


class LeaderPullbackStrategy(BaseStrategy):
    strategy_name = "leader_pullback"

    def __init__(self, config=None):
        super().__init__(config=config)
        self.default_qty = max(1, int(self.config.get("default_order_qty", 1) or 1))
        self.leader_entry_start_hhmm = str(self.config.get("leader_entry_start_hhmm", "09:05") or "09:05")
        self.leader_initial_rally_pct = float(self.config.get("leader_initial_rally_pct", 0.4) or 0.4)
        self.leader_pullback_min_pct = float(self.config.get("leader_pullback_min_pct", 0.3) or 0.3)
        self.leader_pullback_max_pct = float(self.config.get("leader_pullback_max_pct", 2.0) or 2.0)
        self.leader_price_change_floor = float(self.config.get("leader_price_change_floor", 0.1) or 0.1)
        self.leader_volume_ratio_floor = float(self.config.get("leader_volume_ratio_floor", 0.6) or 0.6)
        self.leader_strength_floor = float(self.config.get("leader_strength_floor", 70.0) or 70.0)
        self.leader_support_open_tolerance_pct = float(
            self.config.get("leader_support_open_tolerance_pct", 0.2) or 0.2
        )
        self.leader_rally_by_change_pct = float(self.config.get("leader_rally_by_change_pct", 0.3) or 0.3)
        self.leader_rally_by_volume_ratio = float(self.config.get("leader_rally_by_volume_ratio", 0.8) or 0.8)
        self.leader_state: dict[str, dict[str, Any]] = {}

    def _time_hhmm(self, tick) -> str:
        ts = getattr(tick, "ts", None)
        if isinstance(ts, datetime):
            return ts.strftime("%H:%M")
        return datetime.now().strftime("%H:%M")

    def _get_symbol_state(self, symbol: str, tick) -> dict[str, Any]:
        state = self.leader_state.setdefault(
            symbol,
            {
                "trade_date": getattr(tick, "ts", datetime.now()).strftime("%Y-%m-%d"),
                "tick_count": 0,
                "open_price": 0.0,
                "intraday_high": 0.0,
                "prev_price": 0.0,
                "rally_seen": False,
            },
        )
        current_trade_date = getattr(tick, "ts", datetime.now()).strftime("%Y-%m-%d")
        if state.get("trade_date") != current_trade_date:
            state.clear()
            state.update(
                {
                    "trade_date": current_trade_date,
                    "tick_count": 0,
                    "open_price": 0.0,
                    "intraday_high": 0.0,
                    "prev_price": 0.0,
                    "rally_seen": False,
                }
            )
        return state

    def _update_symbol_state(self, symbol: str, tick) -> dict[str, Any]:
        state = self._get_symbol_state(symbol, tick)
        price = float(getattr(tick, "price", 0.0) or 0.0)
        state["tick_count"] = int(state.get("tick_count", 0)) + 1
        if float(state.get("open_price", 0.0) or 0.0) <= 0.0 and price > 0.0:
            state["open_price"] = price
        state["intraday_high"] = max(float(state.get("intraday_high", price) or price), price)

        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)
        if (
            price >= float(state.get("open_price", price) or price) * (1.0 + self.leader_initial_rally_pct / 100.0)
            or price_change_pct >= self.leader_rally_by_change_pct
            or volume_ratio >= self.leader_rally_by_volume_ratio
        ):
            state["rally_seen"] = True
        return state

    def generate_signal(self, tick, portfolio=None):
        self.last_reject_reason = ""

        def reject(reason: str):
            self.last_reject_reason = reason
            if symbol:
                self.leader_state.setdefault(symbol, {})["prev_price"] = price
            return None

        symbol = str(getattr(tick, "symbol", "")).strip()
        if not symbol:
            self.last_reject_reason = "symbol empty"
            return None

        if portfolio is not None and hasattr(portfolio, "has_position") and portfolio.has_position(symbol):
            self.last_reject_reason = "already has position"
            return None

        state = self._update_symbol_state(symbol, tick)
        price = float(getattr(tick, "price", 0.0) or 0.0)
        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)
        trade_strength = float(getattr(tick, "trade_strength", 0.0) or 0.0)

        if price <= 0:
            return reject("invalid price")
        if self._time_hhmm(tick) < self.leader_entry_start_hhmm:
            return reject(f"leader_wait<{self.leader_entry_start_hhmm}")
        if not bool(state.get("rally_seen", False)):
            return reject("leader_rally_not_seen")

        open_price = float(state.get("open_price", 0.0) or 0.0)
        intraday_high = float(state.get("intraday_high", price) or price)
        prev_price = float(state.get("prev_price", 0.0) or 0.0)
        if open_price <= 0 or intraday_high <= 0:
            return reject("leader_state_invalid")

        pullback_pct = ((intraday_high - price) / intraday_high) * 100.0 if intraday_high else 0.0
        support_floor = open_price * (1.0 - self.leader_support_open_tolerance_pct / 100.0)
        rebound_confirmed = price > prev_price if prev_price > 0 else False

        if pullback_pct < self.leader_pullback_min_pct:
            return reject(f"leader_pullback<{self.leader_pullback_min_pct}")
        if pullback_pct > self.leader_pullback_max_pct:
            return reject(f"leader_pullback>{self.leader_pullback_max_pct}")
        if price < support_floor:
            return reject("leader_open_support_broken")
        if not rebound_confirmed:
            return reject("leader_rebound_not_confirmed")
        if price_change_pct < self.leader_price_change_floor:
            return reject(f"leader_price_change<{self.leader_price_change_floor}")
        if volume_ratio < self.leader_volume_ratio_floor:
            return reject(f"leader_volume_ratio<{self.leader_volume_ratio_floor}")
        if 0.0 < trade_strength < self.leader_strength_floor:
            return reject(f"leader_strength<{self.leader_strength_floor}")

        leader_value = float(getattr(tick, "leader_score", 0.0) or 0.0)
        theme_value = float(getattr(tick, "theme_score", 0.0) or 0.0)
        news_value = float(getattr(tick, "news_score", 0.0) or 0.0)
        state["prev_price"] = price
        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=self.default_qty,
            reason=(
                "leader_pullback_entry"
                f" | pullback={pullback_pct:.2f}"
                f" | chg={price_change_pct:.2f}"
                f" | vr={volume_ratio:.2f}"
                f" | strength={trade_strength:.1f}"
                f" | news={news_value:.1f}"
                f" | theme={theme_value:.1f}"
                f" | leader={leader_value:.1f}"
            ),
            price=price,
            order_type=OrderType.MARKET,
            ts=getattr(tick, "ts", datetime.now()),
        )

    def mark_entry(self, symbol: str, ts):
        return None
