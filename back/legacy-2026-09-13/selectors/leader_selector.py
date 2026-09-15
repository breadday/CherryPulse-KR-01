from __future__ import annotations

from datetime import datetime

from .base_selector import BaseSelector


class LeaderSelector(BaseSelector):
    def __init__(self, config=None):
        self.config = config or {}
        self.selector_name = "leader_selector"
        self.universe_name = "leader_universe"
        self.start_hhmm = str(
            self.config.get("leader_selector_start_hhmm", self.config.get("leader_entry_start_hhmm", "09:00"))
            or "09:00"
        )
        self.min_price = float(self.config.get("leader_selector_min_price", 1) or 1)
        self.min_price_change_pct = float(
            self.config.get(
                "leader_selector_min_price_change_pct",
                self.config.get("leader_price_change_floor", 0.0),
            )
            or 0.0
        )
        self.min_volume_ratio = float(
            self.config.get(
                "leader_selector_min_volume_ratio",
                self.config.get("leader_volume_ratio_floor", 0.5),
            )
            or 0.5
        )
        self.min_interest_score = float(self.config.get("leader_selector_min_interest_score", 0.0) or 0.0)

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

        price = float(getattr(tick, "price", 0.0) or 0.0)
        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)
        news_score = float(getattr(tick, "news_score", 0.0) or 0.0)
        theme_score = float(getattr(tick, "theme_score", 0.0) or 0.0)
        leader_score = float(getattr(tick, "leader_score", 0.0) or 0.0)
        interest_score = news_score + theme_score + leader_score

        if price < self.min_price:
            return False, f"selector_price<{self.min_price}"
        if self._time_hhmm(tick) < self.start_hhmm:
            return False, f"selector_wait<{self.start_hhmm}"
        if price_change_pct < self.min_price_change_pct and volume_ratio < self.min_volume_ratio:
            return False, f"selector_chg_vr<{self.min_price_change_pct}/{self.min_volume_ratio}"
        if self.min_interest_score > 0 and interest_score < self.min_interest_score:
            return False, f"selector_interest<{self.min_interest_score}"
        return True, ""
