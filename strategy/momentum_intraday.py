# -*- coding: utf-8 -*-
# strategy/momentum_intraday.py

from __future__ import annotations

from datetime import datetime

from core.models import OrderType, Signal, Side


class MomentumIntradayStrategy:
    def __init__(self, config=None):
        self.config = config or {}
        self.last_reject_reason = ""
        self.last_entry_at = {}

        self.min_trade_strength = float(self.config.get("min_trade_strength", 110) or 110)
        self.min_price_change_pct = float(self.config.get("min_price_change_pct", 0.3) or 0.3)
        self.min_volume_ratio = float(self.config.get("min_volume_ratio", 1.1) or 1.1)
        self.entry_volume_ratio_min = float(self.config.get("entry_volume_ratio_min", 1.0) or 1.0)
        self.volume_ratio_hard_floor = float(self.config.get("volume_ratio_hard_floor", 0.8) or 0.8)
        self.use_score_filter = bool(self.config.get("use_score_filter", True))
        self.min_entry_score = float(self.config.get("min_entry_score", 58) or 58)
        self.default_qty = max(1, int(self.config.get("default_order_qty", 1) or 1))

    def _score_signal(self, tick) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        trade_strength = float(getattr(tick, "trade_strength", 0.0) or 0.0)
        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)
        news_score = float(getattr(tick, "news_score", 0.0) or 0.0)
        theme_score = float(getattr(tick, "theme_score", 0.0) or 0.0)
        leader_score = float(getattr(tick, "leader_score", 0.0) or 0.0)

        if trade_strength >= self.min_trade_strength:
            score += min(30.0, (trade_strength - self.min_trade_strength) * 0.5 + 15.0)
            reasons.append(f"strength={trade_strength:.1f}")

        if price_change_pct >= self.min_price_change_pct:
            score += min(20.0, price_change_pct * 8.0)
            reasons.append(f"chg={price_change_pct:.2f}")

        if volume_ratio >= self.entry_volume_ratio_min:
            score += min(20.0, volume_ratio * 8.0)
            reasons.append(f"vr={volume_ratio:.2f}")

        if news_score > 0:
            score += min(10.0, news_score * 0.2)
            reasons.append(f"news={news_score:.1f}")

        if theme_score > 0:
            score += min(10.0, theme_score * 0.2)
            reasons.append(f"theme={theme_score:.1f}")

        if leader_score > 0:
            score += min(10.0, leader_score * 0.2)
            reasons.append(f"leader={leader_score:.1f}")

        return score, reasons

    def generate_signal(self, tick, portfolio=None):
        self.last_reject_reason = ""

        symbol = str(getattr(tick, "symbol", "")).strip()
        if not symbol:
            self.last_reject_reason = "symbol empty"
            return None

        if portfolio is not None and hasattr(portfolio, "has_position") and portfolio.has_position(symbol):
            self.last_reject_reason = "already has position"
            return None

        trade_strength = float(getattr(tick, "trade_strength", 0.0) or 0.0)
        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)
        price = float(getattr(tick, "price", 0.0) or 0.0)

        if price <= 0:
            self.last_reject_reason = "invalid price"
            return None

        if price_change_pct < self.min_price_change_pct:
            self.last_reject_reason = f"price_change_pct<{self.min_price_change_pct}"
            return None

        if volume_ratio < self.volume_ratio_hard_floor:
            self.last_reject_reason = f"volume_ratio<{self.volume_ratio_hard_floor}"
            return None

        if volume_ratio < self.min_volume_ratio:
            self.last_reject_reason = f"volume_ratio<{self.min_volume_ratio}"
            return None

        if trade_strength < self.min_trade_strength:
            self.last_reject_reason = f"trade_strength<{self.min_trade_strength}"
            return None

        score, score_reasons = self._score_signal(tick)
        if self.use_score_filter and score < self.min_entry_score:
            self.last_reject_reason = f"score<{self.min_entry_score} ({score:.1f})"
            return None

        reason_parts = ["entry", f"score={score:.1f}"] + score_reasons
        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=self.default_qty,
            reason=" | ".join(reason_parts),
            price=price,
            order_type=OrderType.MARKET,
            ts=getattr(tick, "ts", datetime.now()),
        )

    def mark_entry(self, symbol: str, ts):
        self.last_entry_at[str(symbol).strip()] = ts
