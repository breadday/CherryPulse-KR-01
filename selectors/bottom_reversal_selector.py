from __future__ import annotations

from datetime import datetime

from .base_selector import BaseSelector


class BottomReversalSelector(BaseSelector):
    """바닥권 회복 후보를 고르는 1차 필터입니다."""

    def __init__(self, config=None):
        self.config = config or {}
        self.selector_name = "bottom_reversal_selector"
        self.universe_name = "bottom_reversal_universe"
        self.start_hhmm = str(self.config.get("bottom_reversal_selector_start_hhmm", "09:35") or "09:35")
        self.end_hhmm = str(self.config.get("bottom_reversal_selector_end_hhmm", "14:20") or "14:20")
        self.min_price = float(self.config.get("bottom_reversal_min_price", 1_000) or 1_000)
        self.min_price_change_pct = float(self.config.get("bottom_reversal_min_price_change_pct", -3.5) or -3.5)
        self.max_price_change_pct = float(self.config.get("bottom_reversal_max_price_change_pct", 4.0) or 4.0)
        self.min_volume_ratio = float(self.config.get("bottom_reversal_min_volume_ratio", 0.4) or 0.4)

    def select(self) -> list[str]:
        return []

    def _time_hhmm(self, tick) -> str:
        ts = getattr(tick, "ts", None)
        if isinstance(ts, datetime):
            return ts.strftime("%H:%M")
        return datetime.now().strftime("%H:%M")

    def matches_tick(self, tick) -> tuple[bool, str]:
        symbol = str(getattr(tick, "symbol", "")).strip()
        if not symbol:
            return False, "selector_symbol_empty"
        allowed, reason = self._matches_strategy_universe(symbol, self.universe_name)
        if not allowed:
            return False, reason

        hhmm = self._time_hhmm(tick)
        price = float(getattr(tick, "price", 0.0) or 0.0)
        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)

        if hhmm < self.start_hhmm:
            return False, f"bottom_selector_wait<{self.start_hhmm}"
        if hhmm > self.end_hhmm:
            return False, f"bottom_selector_closed>{self.end_hhmm}"
        if price < self.min_price:
            return False, f"bottom_selector_price<{self.min_price}"
        if price_change_pct < self.min_price_change_pct:
            return False, f"bottom_selector_chg<{self.min_price_change_pct}"
        if price_change_pct > self.max_price_change_pct:
            return False, f"bottom_selector_chg>{self.max_price_change_pct}"
        if volume_ratio < self.min_volume_ratio:
            return False, f"bottom_selector_vr<{self.min_volume_ratio}"
        return True, ""
