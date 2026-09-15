from __future__ import annotations

from .base_selector import BaseSelector


class MomentumSelector(BaseSelector):
    def __init__(self, config=None):
        self.config = config or {}
        self.selector_name = "momentum_selector"
        self.universe_name = "momentum_universe"
        self.min_price = float(self.config.get("momentum_selector_min_price", 1) or 1)
        self.min_price_change_pct = float(
            self.config.get(
                "momentum_selector_min_price_change_pct",
                self.config.get("min_price_change_pct", 0.1),
            )
            or 0.1
        )
        self.min_volume_ratio = float(
            self.config.get(
                "momentum_selector_min_volume_ratio",
                self.config.get("volume_ratio_hard_floor", 0.5),
            )
            or 0.5
        )
        self.min_trade_strength = float(
            self.config.get("momentum_selector_min_trade_strength", 0.0) or 0.0
        )

    def select(self) -> list[str]:
        return []

    def matches_tick(self, tick) -> tuple[bool, str]:
        symbol = str(getattr(tick, "symbol", "")).strip()
        if not symbol:
            return False, "selector_symbol_empty"
        allowed, reason = self._matches_strategy_universe(symbol, self.universe_name)
        if not allowed:
            return False, reason

        price = float(getattr(tick, "price", 0.0) or 0.0)
        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)
        trade_strength = float(getattr(tick, "trade_strength", 0.0) or 0.0)

        if price < self.min_price:
            return False, f"selector_price<{self.min_price}"
        if price_change_pct < self.min_price_change_pct:
            return False, f"selector_chg<{self.min_price_change_pct}"
        if volume_ratio < self.min_volume_ratio:
            return False, f"selector_vr<{self.min_volume_ratio}"
        if self.min_trade_strength > 0 and 0.0 < trade_strength < self.min_trade_strength:
            return False, f"selector_strength<{self.min_trade_strength}"
        return True, ""
