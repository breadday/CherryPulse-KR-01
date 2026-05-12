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
        self.use_rsi2 = bool(self.config.get("close_buy_use_rsi2", True))
        self.max_rsi2 = float(self.config.get("close_buy_signal_max_rsi2", 30.0) or 30.0)
        self.rsi_sample_seconds = max(1, int(self.config.get("close_buy_rsi_sample_seconds", 60) or 60))
        self.rsi_max_samples = max(4, int(self.config.get("close_buy_rsi_max_samples", 30) or 30))
        self.min_recovery_from_low_pct = float(self.config.get("close_buy_min_recovery_from_low_pct", 0.3) or 0.3)
        self.max_pullback_from_high_pct = float(self.config.get("close_buy_max_pullback_from_high_pct", 4.5) or 4.5)
        self.daily_candidate_mode = bool(self.config.get("daily_candidate_mode", False))
        self.daily_candidate_max_gap_pct = float(self.config.get("daily_candidate_max_gap_pct", 5.0) or 5.0)
        self.daily_candidate_min_change_pct = float(self.config.get("daily_candidate_min_change_pct", -3.0) or -3.0)
        self.last_entry_date: dict[str, str] = {}
        self.symbol_state: dict[str, dict] = {}

    def _trade_date(self, tick) -> str:
        ts = getattr(tick, "ts", None)
        if isinstance(ts, datetime):
            return ts.strftime("%Y-%m-%d")
        return datetime.now().strftime("%Y-%m-%d")

    def _update_symbol_state(self, tick, price: float) -> dict:
        symbol = str(getattr(tick, "symbol", "")).strip()
        ts = getattr(tick, "ts", None)
        if not isinstance(ts, datetime):
            ts = datetime.now()

        trade_date = ts.strftime("%Y-%m-%d")
        state = self.symbol_state.get(symbol)
        if not state or state.get("trade_date") != trade_date:
            state = {
                "trade_date": trade_date,
                "high": price,
                "low": price,
                "samples": [],
                "last_sample_ts": 0.0,
            }
            self.symbol_state[symbol] = state

        state["high"] = max(float(state.get("high", price) or price), price)
        state["low"] = min(float(state.get("low", price) or price), price)

        sample_ts = ts.timestamp()
        samples = state.setdefault("samples", [])
        last_sample_ts = float(state.get("last_sample_ts", 0.0) or 0.0)
        if not samples or sample_ts - last_sample_ts >= self.rsi_sample_seconds:
            samples.append(price)
            state["last_sample_ts"] = sample_ts
            if len(samples) > self.rsi_max_samples:
                del samples[: len(samples) - self.rsi_max_samples]
        elif samples:
            # 같은 1분 구간에서는 마지막 가격을 갱신해 장마감 현재가를 반영합니다.
            samples[-1] = price

        return state

    @staticmethod
    def _calc_rsi2(samples: list[float]):
        if len(samples) < 3:
            return None

        changes = []
        for prev, curr in zip(samples[-3:-1], samples[-2:]):
            changes.append(float(curr) - float(prev))

        gains = [max(change, 0.0) for change in changes]
        losses = [abs(min(change, 0.0)) for change in changes]
        avg_gain = sum(gains) / 2.0
        avg_loss = sum(losses) / 2.0
        if avg_loss <= 0:
            return 100.0
        if avg_gain <= 0:
            return 0.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

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
        state = self._update_symbol_state(tick, price)
        high_price = float(state.get("high", price) or price)
        low_price = float(state.get("low", price) or price)
        pullback_from_high_pct = ((high_price - price) / high_price * 100.0) if high_price > 0 else 0.0
        recovery_from_low_pct = ((price - low_price) / low_price * 100.0) if low_price > 0 else 0.0
        rsi2 = self._calc_rsi2(list(state.get("samples", [])))

        if price <= 0:
            self.last_reject_reason = "invalid price"
            return None

        if self.daily_candidate_mode:
            if price_change_pct < self.daily_candidate_min_change_pct:
                self.last_reject_reason = f"daily_candidate_chg<{self.daily_candidate_min_change_pct}"
                return None
            if price_change_pct > self.daily_candidate_max_gap_pct:
                self.last_reject_reason = f"daily_candidate_chg>{self.daily_candidate_max_gap_pct}"
                return None
            return Signal(
                symbol=symbol,
                side=Side.BUY,
                qty=self.default_qty,
                reason=(
                    "daily_close_buy_entry"
                    f" | chg={price_change_pct:.2f}"
                    f" | vr={volume_ratio:.2f}"
                    f" | strength={trade_strength:.1f}"
                ),
                price=price,
                order_type=OrderType.MARKET,
                ts=getattr(tick, "ts", datetime.now()),
            )

        if price_change_pct < self.min_price_change_pct:
            self.last_reject_reason = f"close_buy_chg<{self.min_price_change_pct}"
            return None
        if price_change_pct > self.max_price_change_pct:
            self.last_reject_reason = f"close_buy_chg>{self.max_price_change_pct}"
            return None
        if volume_ratio < self.min_volume_ratio:
            self.last_reject_reason = f"close_buy_vr<{self.min_volume_ratio}"
            return None
        if self.use_rsi2:
            if rsi2 is None:
                self.last_reject_reason = "close_buy_rsi2_not_ready"
                return None
            if rsi2 > self.max_rsi2:
                self.last_reject_reason = f"close_buy_rsi2>{self.max_rsi2}"
                return None
        if recovery_from_low_pct < self.min_recovery_from_low_pct:
            self.last_reject_reason = f"close_buy_recovery<{self.min_recovery_from_low_pct}"
            return None
        if pullback_from_high_pct > self.max_pullback_from_high_pct:
            self.last_reject_reason = f"close_buy_pullback>{self.max_pullback_from_high_pct}"
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
                f" | rsi2={(rsi2 if rsi2 is not None else -1):.1f}"
                f" | pullback={pullback_from_high_pct:.2f}"
                f" | recovery={recovery_from_low_pct:.2f}"
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
