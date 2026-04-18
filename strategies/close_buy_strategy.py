from __future__ import annotations

from datetime import datetime

from core.models import OrderType, Signal, Side
from .base_strategy import BaseStrategy


class CloseBuyStrategy(BaseStrategy):
    strategy_name = "close_buy"

    def __init__(self, config=None):
        super().__init__(config=config)
        self.default_qty = max(1, int(self.config.get("default_order_qty", 1) or 1))
        self.min_price_change_pct = float(self.config.get("close_buy_signal_min_price_change_pct", 1.5) or 1.5)
        self.min_volume_ratio = float(self.config.get("close_buy_signal_min_volume_ratio", 1.1) or 1.1)
        self.min_trade_strength = float(self.config.get("close_buy_signal_min_trade_strength", 0.0) or 0.0)
        self.max_price_change_pct = float(self.config.get("close_buy_signal_max_price_change_pct", 7.0) or 7.0)
        self.min_total_score = float(self.config.get("close_buy_signal_min_total_score", 0.0) or 0.0)
        self.last_entry_date: dict[str, str] = {}

    def _trade_date(self, tick) -> str:
        ts = getattr(tick, "ts", None)
        if isinstance(ts, datetime):
            return ts.strftime("%Y-%m-%d")
        return datetime.now().strftime("%Y-%m-%d")

    def generate_signal(self, tick, portfolio=None):
        self.last_reject_reason = ""

        symbol = str(getattr(tick, "symbol", "")).strip()
        if not symbol:
            self.last_reject_reason = "symbol empty"
            return None

        if portfolio is not None and hasattr(portfolio, "has_position") and portfolio.has_position(symbol):
            self.last_reject_reason = "already has position"
            return None

        trade_date = self._trade_date(tick)
        if self.last_entry_date.get(symbol) == trade_date:
            self.last_reject_reason = "close_buy_already_entered_today"
            return None

        price = float(getattr(tick, "price", 0.0) or 0.0)
        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)
        trade_strength = float(getattr(tick, "trade_strength", 0.0) or 0.0)
        news_score = float(getattr(tick, "news_score", 0.0) or 0.0)
        theme_score = float(getattr(tick, "theme_score", 0.0) or 0.0)
        leader_score = float(getattr(tick, "leader_score", 0.0) or 0.0)
        total_score = news_score + theme_score + leader_score

        if price <= 0:
            self.last_reject_reason = "invalid price"
            return None
        if price_change_pct < self.min_price_change_pct:
            self.last_reject_reason = f"close_buy_chg<{self.min_price_change_pct}"
            return None
        if price_change_pct > self.max_price_change_pct:
            self.last_reject_reason = f"close_buy_chg>{self.max_price_change_pct}"
            return None
        if volume_ratio < self.min_volume_ratio:
            self.last_reject_reason = f"close_buy_vr<{self.min_volume_ratio}"
            return None
        if self.min_trade_strength > 0 and 0.0 < trade_strength < self.min_trade_strength:
            self.last_reject_reason = f"close_buy_strength<{self.min_trade_strength}"
            return None
        if self.min_total_score > 0 and total_score < self.min_total_score:
            self.last_reject_reason = f"close_buy_score<{self.min_total_score}"
            return None

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=self.default_qty,
            reason=(
                "close_buy_entry"
                f" | chg={price_change_pct:.2f}"
                f" | vr={volume_ratio:.2f}"
                f" | strength={trade_strength:.1f}"
                f" | news={news_score:.1f}"
                f" | theme={theme_score:.1f}"
                f" | leader={leader_score:.1f}"
            ),
            price=price,
            order_type=OrderType.MARKET,
            ts=getattr(tick, "ts", datetime.now()),
        )

    def mark_entry(self, symbol: str, ts):
        trade_date = ts.strftime("%Y-%m-%d") if isinstance(ts, datetime) else datetime.now().strftime("%Y-%m-%d")
        self.last_entry_date[str(symbol).strip()] = trade_date
