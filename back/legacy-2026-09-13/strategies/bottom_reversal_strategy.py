from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime

from core.models import OrderType, Signal, Side
from .base_strategy import BaseStrategy


class BottomReversalStrategy(BaseStrategy):
    """바닥권에서 첫 회복 모멘텀이 확인될 때만 진입합니다."""

    strategy_name = "bottom_reversal"

    def __init__(self, config=None):
        super().__init__(config=config)
        self.default_qty = max(1, int(self.config.get("default_order_qty", 1) or 1))
        self.require_daily_pattern = bool(self.config.get("bottom_reversal_require_daily_pattern", True))
        self.daily_min_candles = max(10, int(self.config.get("bottom_reversal_daily_min_candles", 20) or 20))
        self.daily_lookback = max(self.daily_min_candles, int(self.config.get("bottom_reversal_daily_lookback", 30) or 30))
        self.daily_min_decline_pct = float(self.config.get("bottom_reversal_daily_min_decline_pct", 12.0) or 12.0)
        self.daily_near_low_pct = float(self.config.get("bottom_reversal_daily_near_low_pct", 12.0) or 12.0)
        self.daily_recovery_from_low_pct = float(
            self.config.get("bottom_reversal_daily_recovery_from_low_pct", 3.0) or 3.0
        )
        self.daily_min_volume_ratio = float(
            self.config.get("bottom_reversal_daily_min_volume_ratio", 1.0) or 1.0
        )
        self.daily_ma_short = max(3, int(self.config.get("bottom_reversal_daily_ma_short", 5) or 5))
        self.daily_ma_mid = max(self.daily_ma_short + 1, int(self.config.get("bottom_reversal_daily_ma_mid", 20) or 20))
        self.daily_w_low_tolerance_pct = float(
            self.config.get("bottom_reversal_daily_w_low_tolerance_pct", 5.0) or 5.0
        )
        self.daily_w_min_separation = max(3, int(self.config.get("bottom_reversal_daily_w_min_separation", 5) or 5))
        self.daily_v_recovery_pct = float(self.config.get("bottom_reversal_daily_v_recovery_pct", 5.0) or 5.0)
        self.daily_rounded_rising_days = max(
            2,
            int(self.config.get("bottom_reversal_daily_rounded_rising_days", 2) or 2),
        )
        self.history_size = max(20, int(self.config.get("bottom_reversal_history_size", 80) or 80))
        self.min_history = max(10, int(self.config.get("bottom_reversal_min_history", 25) or 25))
        self.short_window = max(3, int(self.config.get("bottom_reversal_short_window", 5) or 5))
        self.long_window = max(self.short_window + 1, int(self.config.get("bottom_reversal_long_window", 20) or 20))
        self.pattern_lookback = max(
            self.long_window + 5,
            int(self.config.get("bottom_reversal_pattern_lookback", 50) or 50),
        )
        self.min_ticks_after_low = max(
            1,
            int(self.config.get("bottom_reversal_min_ticks_after_low", 3) or 3),
        )
        self.require_pattern = bool(self.config.get("bottom_reversal_require_pattern", True))
        self.enable_w_bottom = bool(self.config.get("bottom_reversal_enable_w_bottom", True))
        self.enable_v_reversal = bool(self.config.get("bottom_reversal_enable_v_reversal", True))
        self.enable_rounded_bottom = bool(self.config.get("bottom_reversal_enable_rounded_bottom", True))
        self.w_min_separation = max(3, int(self.config.get("bottom_reversal_w_min_separation", 6) or 6))
        self.w_low_tolerance_pct = float(self.config.get("bottom_reversal_w_low_tolerance_pct", 1.2) or 1.2)
        self.w_undercut_tolerance_pct = float(
            self.config.get("bottom_reversal_w_undercut_tolerance_pct", 0.6) or 0.6
        )
        self.w_neckline_break_pct = float(self.config.get("bottom_reversal_w_neckline_break_pct", 0.05) or 0.05)
        self.v_drop_pct = float(self.config.get("bottom_reversal_v_drop_pct", 1.0) or 1.0)
        self.v_recovery_pct = float(self.config.get("bottom_reversal_v_recovery_pct", 0.8) or 0.8)
        self.rounded_rising_ticks = max(2, int(self.config.get("bottom_reversal_rounded_rising_ticks", 3) or 3))
        self.min_recovery_from_low_pct = float(
            self.config.get("bottom_reversal_min_recovery_from_low_pct", 0.4) or 0.4
        )
        self.max_recovery_from_low_pct = float(
            self.config.get("bottom_reversal_max_recovery_from_low_pct", 3.0) or 3.0
        )
        self.max_pullback_from_high_pct = float(
            self.config.get("bottom_reversal_max_pullback_from_high_pct", 5.0) or 5.0
        )
        self.min_last_momentum_pct = float(
            self.config.get("bottom_reversal_min_last_momentum_pct", 0.12) or 0.12
        )
        self.min_volume_ratio = float(self.config.get("bottom_reversal_signal_min_volume_ratio", 0.7) or 0.7)
        self.min_trade_strength = float(self.config.get("bottom_reversal_signal_min_trade_strength", 80.0) or 80.0)
        self.min_price_change_pct = float(
            self.config.get("bottom_reversal_signal_min_price_change_pct", -3.0) or -3.0
        )
        self.max_price_change_pct = float(
            self.config.get("bottom_reversal_signal_max_price_change_pct", 4.0) or 4.0
        )
        self.cooldown_sec = max(0, int(self.config.get("bottom_reversal_entry_cooldown_sec", 900) or 900))
        self.price_history = defaultdict(lambda: deque(maxlen=self.history_size))
        self.last_entry_at = {}

    def _append_price(self, symbol: str, price: float):
        if price > 0:
            self.price_history[symbol].append(float(price))

    def _avg(self, values) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _pct(self, current: float, base: float) -> float:
        if base <= 0:
            return 0.0
        return (current - base) / base * 100.0

    def _normalize_daily_candles(self, candles) -> list[dict]:
        today = datetime.now().strftime("%Y%m%d")
        clean = []
        for candle in candles or []:
            if not isinstance(candle, dict):
                continue
            date = str(candle.get("date", "") or "").strip()
            close_price = float(candle.get("close", 0.0) or 0.0)
            if close_price <= 0:
                continue
            # 당일 진행 중 일봉은 완성된 일봉 패턴 판정에서 제외합니다.
            if date and date >= today:
                continue
            clean.append(
                {
                    "date": date,
                    "open": float(candle.get("open", close_price) or close_price),
                    "high": float(candle.get("high", close_price) or close_price),
                    "low": float(candle.get("low", close_price) or close_price),
                    "close": close_price,
                    "volume": float(candle.get("volume", 0.0) or 0.0),
                }
            )
        clean.sort(key=lambda row: row.get("date", ""))
        return clean

    def _detect_daily_w_bottom(self, candles: list[dict]) -> tuple[bool, str, dict]:
        recent = candles[-self.daily_lookback:]
        if len(recent) < self.daily_w_min_separation * 2 + 3:
            return False, "", {}

        lows = [row["low"] for row in recent]
        closes = [row["close"] for row in recent]
        first_zone_end = max(1, int(len(recent) * 0.65))
        first_low_idx = min(range(first_zone_end), key=lambda idx: lows[idx])
        second_start = first_low_idx + self.daily_w_min_separation
        if second_start >= len(recent) - 1:
            return False, "", {}
        second_low_idx = min(range(second_start, len(recent)), key=lambda idx: lows[idx])

        first_low = lows[first_low_idx]
        second_low = lows[second_low_idx]
        if first_low <= 0 or second_low <= 0:
            return False, "", {}

        low_gap_pct = abs(second_low - first_low) / first_low * 100.0
        if low_gap_pct > self.daily_w_low_tolerance_pct:
            return False, "", {}

        middle_high = max(row["high"] for row in recent[first_low_idx + 1:second_low_idx] or recent)
        last_close = closes[-1]
        ma_short = self._avg(closes[-self.daily_ma_short:])
        # 목선 돌파 전이라도 5일선 회복이 나오면 "오르기 시작"으로 인정합니다.
        if last_close < middle_high * 0.98 and last_close < ma_short:
            return False, "", {}

        return True, "daily_w_bottom", {
            "daily_first_low": first_low,
            "daily_second_low": second_low,
            "daily_neckline": middle_high,
            "daily_low_gap_pct": low_gap_pct,
        }

    def _detect_daily_v_reversal(self, candles: list[dict], decline_pct: float, recovery_pct: float) -> tuple[bool, str, dict]:
        recent = candles[-self.daily_lookback:]
        lows = [row["low"] for row in recent]
        closes = [row["close"] for row in recent]
        low_idx = min(range(len(recent)), key=lambda idx: lows[idx])
        if len(recent) - 1 - low_idx < 2:
            return False, "", {}
        if decline_pct < self.daily_min_decline_pct or recovery_pct < self.daily_v_recovery_pct:
            return False, "", {}
        if len(closes) < 3 or not (closes[-1] >= closes[-2] >= closes[-3]):
            return False, "", {}
        return True, "daily_v_reversal", {
            "daily_decline_pct": decline_pct,
            "daily_recovery_pct": recovery_pct,
        }

    def _detect_daily_rounded_bottom(self, candles: list[dict], recovery_pct: float) -> tuple[bool, str, dict]:
        recent = candles[-self.daily_lookback:]
        closes = [row["close"] for row in recent]
        lows = [row["low"] for row in recent]
        if len(closes) < self.daily_ma_mid:
            return False, "", {}
        low_idx = min(range(len(recent)), key=lambda idx: lows[idx])
        if len(recent) - 1 - low_idx < self.daily_rounded_rising_days:
            return False, "", {}
        ma_short = self._avg(closes[-self.daily_ma_short:])
        prev_ma_short = self._avg(closes[-self.daily_ma_short - 1:-1])
        ma_mid = self._avg(closes[-self.daily_ma_mid:])
        if closes[-1] < ma_short:
            return False, "", {}
        if ma_short < prev_ma_short:
            return False, "", {}
        if recovery_pct < self.daily_recovery_from_low_pct and ma_short < ma_mid:
            return False, "", {}
        return True, "daily_rounded_bottom", {
            "daily_recovery_pct": recovery_pct,
            "daily_ma5": ma_short,
            "daily_ma20": ma_mid,
        }

    def _detect_daily_bottom_pattern(self, candles) -> tuple[bool, str, dict]:
        daily = self._normalize_daily_candles(candles)
        if len(daily) < self.daily_min_candles:
            return False, "daily_candles_not_ready", {"daily_count": len(daily)}

        recent = daily[-self.daily_lookback:]
        highs = [row["high"] for row in recent]
        lows = [row["low"] for row in recent]
        closes = [row["close"] for row in recent]
        volumes = [row.get("volume", 0.0) for row in recent]
        recent_high = max(highs)
        recent_low = min(lows)
        last_close = closes[-1]
        decline_pct = max(0.0, (recent_high - recent_low) / recent_high * 100.0) if recent_high > 0 else 0.0
        near_low_pct = (last_close - recent_low) / recent_low * 100.0 if recent_low > 0 else 999.0
        recovery_pct = near_low_pct
        volume_base = self._avg(volumes[-21:-1]) if len(volumes) >= 21 else self._avg(volumes[:-1])
        volume_ratio = volumes[-1] / volume_base if volume_base > 0 else 1.0

        if decline_pct < self.daily_min_decline_pct:
            return False, "daily_decline_not_enough", {"daily_decline_pct": decline_pct}
        if near_low_pct > self.daily_near_low_pct:
            return False, "daily_too_far_from_low", {"daily_near_low_pct": near_low_pct}
        if volume_ratio < self.daily_min_volume_ratio:
            return False, "daily_volume_not_enough", {"daily_volume_ratio": volume_ratio}

        detectors = (
            self._detect_daily_w_bottom(recent),
            self._detect_daily_v_reversal(recent, decline_pct, recovery_pct),
            self._detect_daily_rounded_bottom(recent, recovery_pct),
        )
        for matched, pattern_name, details in detectors:
            if matched:
                details.update(
                    {
                        "daily_decline_pct": decline_pct,
                        "daily_recovery_pct": recovery_pct,
                        "daily_volume_ratio": volume_ratio,
                        "daily_last_close": last_close,
                    }
                )
                return True, pattern_name, details
        return False, "daily_pattern_not_confirmed", {
            "daily_decline_pct": decline_pct,
            "daily_recovery_pct": recovery_pct,
            "daily_volume_ratio": volume_ratio,
        }

    def _is_recent_sequence_rising(self, prices: list[float], count: int) -> bool:
        if len(prices) < count + 1:
            return False
        recent = prices[-(count + 1):]
        return all(curr >= prev for prev, curr in zip(recent, recent[1:]))

    def _detect_w_bottom(self, prices: list[float], current_price: float) -> tuple[bool, str, dict]:
        if not self.enable_w_bottom or len(prices) < max(self.min_history, self.w_min_separation * 2 + 5):
            return False, "", {}

        search = prices[-self.pattern_lookback:]
        if len(search) < self.w_min_separation * 2 + 5:
            return False, "", {}

        first_zone_end = max(1, int(len(search) * 0.65))
        first_low_idx = min(range(first_zone_end), key=lambda idx: search[idx])
        second_start = first_low_idx + self.w_min_separation
        if second_start >= len(search) - 1:
            return False, "", {}

        second_low_idx = min(range(second_start, len(search)), key=lambda idx: search[idx])
        first_low = search[first_low_idx]
        second_low = search[second_low_idx]
        if first_low <= 0 or second_low <= 0:
            return False, "", {}

        low_gap_pct = abs(second_low - first_low) / first_low * 100.0
        undercut_pct = max(0.0, (first_low - second_low) / first_low * 100.0)
        if second_low < first_low and undercut_pct > self.w_undercut_tolerance_pct:
            return False, "", {}
        if second_low >= first_low and low_gap_pct > self.w_low_tolerance_pct:
            return False, "", {}

        middle = search[first_low_idx + 1:second_low_idx]
        if not middle:
            return False, "", {}
        neckline = max(middle)
        neckline_price = neckline * (1.0 + self.w_neckline_break_pct / 100.0)
        if current_price < neckline_price:
            return False, "", {}

        return True, "w_bottom", {
            "first_low": first_low,
            "second_low": second_low,
            "neckline": neckline,
            "low_gap_pct": low_gap_pct,
        }

    def _detect_v_reversal(self, prices: list[float], current_price: float, recovery_from_low_pct: float) -> tuple[bool, str, dict]:
        if not self.enable_v_reversal or len(prices) < self.min_history:
            return False, "", {}

        search = prices[-self.pattern_lookback:]
        low_idx = min(range(len(search)), key=lambda idx: search[idx])
        if len(search) - 1 - low_idx < self.min_ticks_after_low:
            return False, "", {}

        high_before_low = max(search[:low_idx + 1])
        low_price = search[low_idx]
        drop_pct = max(0.0, (high_before_low - low_price) / high_before_low * 100.0) if high_before_low > 0 else 0.0
        if drop_pct < self.v_drop_pct:
            return False, "", {}
        if recovery_from_low_pct < self.v_recovery_pct:
            return False, "", {}

        return True, "v_reversal", {
            "drop_pct": drop_pct,
            "pattern_low_age": len(search) - 1 - low_idx,
        }

    def _detect_rounded_bottom(self, prices: list[float], current_price: float, short_ma: float, long_ma: float) -> tuple[bool, str, dict]:
        if not self.enable_rounded_bottom or len(prices) < self.long_window:
            return False, "", {}

        search = prices[-self.pattern_lookback:]
        low_idx = min(range(len(search)), key=lambda idx: search[idx])
        low_age = len(search) - 1 - low_idx
        if low_age < self.min_ticks_after_low:
            return False, "", {}
        if current_price < short_ma or short_ma < long_ma:
            return False, "", {}
        if not self._is_recent_sequence_rising(search, self.rounded_rising_ticks):
            return False, "", {}

        return True, "rounded_bottom", {
            "pattern_low_age": low_age,
            "short_ma": short_ma,
            "long_ma": long_ma,
        }

    def _detect_bottom_pattern(
        self,
        prices: list[float],
        current_price: float,
        recovery_from_low_pct: float,
        short_ma: float,
        long_ma: float,
    ) -> tuple[bool, str, dict]:
        detectors = (
            self._detect_w_bottom(prices, current_price),
            self._detect_v_reversal(prices, current_price, recovery_from_low_pct),
            self._detect_rounded_bottom(prices, current_price, short_ma, long_ma),
        )
        for matched, pattern_name, details in detectors:
            if matched:
                return True, pattern_name, details
        return False, "", {}

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
            self.last_reject_reason = "bottom_entry_cooldown"
            return None

        daily_ok, daily_pattern_name, daily_details = self._detect_daily_bottom_pattern(
            getattr(tick, "daily_candles", [])
        )
        if self.require_daily_pattern and not daily_ok:
            self.last_reject_reason = daily_pattern_name
            return None

        history = list(self.price_history[symbol])
        if len(history) < self.min_history:
            self.last_reject_reason = f"bottom_history<{self.min_history}"
            return None

        intraday_low = min(history)
        intraday_high = max(history)
        if intraday_low <= 0 or intraday_high <= 0:
            self.last_reject_reason = "bottom_invalid_range"
            return None

        recovery_from_low_pct = (price - intraday_low) / intraday_low * 100.0
        pullback_from_high_pct = (intraday_high - price) / intraday_high * 100.0
        low_idx = history.index(intraday_low)
        low_age_ticks = len(history) - 1 - low_idx
        prev_price = history[-2] if len(history) >= 2 else price
        last_momentum_pct = (price - prev_price) / prev_price * 100.0 if prev_price > 0 else 0.0
        short_ma = self._avg(history[-self.short_window:])
        long_ma = self._avg(history[-self.long_window:])

        price_change_pct = float(getattr(tick, "price_change_pct", 0.0) or 0.0)
        volume_ratio = float(getattr(tick, "volume_ratio", 0.0) or 0.0)
        trade_strength = float(getattr(tick, "trade_strength", 0.0) or 0.0)

        if price_change_pct < self.min_price_change_pct:
            self.last_reject_reason = f"bottom_chg<{self.min_price_change_pct}"
            return None
        if price_change_pct > self.max_price_change_pct:
            self.last_reject_reason = f"bottom_chg>{self.max_price_change_pct}"
            return None
        if recovery_from_low_pct < self.min_recovery_from_low_pct:
            self.last_reject_reason = f"bottom_recovery<{self.min_recovery_from_low_pct}"
            return None
        if recovery_from_low_pct > self.max_recovery_from_low_pct:
            self.last_reject_reason = f"bottom_recovery>{self.max_recovery_from_low_pct}"
            return None
        if low_age_ticks < self.min_ticks_after_low:
            self.last_reject_reason = f"bottom_low_age<{self.min_ticks_after_low}"
            return None
        if pullback_from_high_pct > self.max_pullback_from_high_pct:
            self.last_reject_reason = f"bottom_pullback>{self.max_pullback_from_high_pct}"
            return None
        if price < short_ma:
            self.last_reject_reason = "bottom_price<short_ma"
            return None
        if short_ma < long_ma:
            self.last_reject_reason = "bottom_short_ma<long_ma"
            return None
        if last_momentum_pct < self.min_last_momentum_pct:
            self.last_reject_reason = f"bottom_momentum<{self.min_last_momentum_pct}"
            return None
        if volume_ratio < self.min_volume_ratio:
            self.last_reject_reason = f"bottom_vr<{self.min_volume_ratio}"
            return None
        if trade_strength < self.min_trade_strength:
            self.last_reject_reason = f"bottom_strength<{self.min_trade_strength}"
            return None

        pattern_ok, pattern_name, pattern_details = self._detect_bottom_pattern(
            history,
            price,
            recovery_from_low_pct,
            short_ma,
            long_ma,
        )
        if self.require_pattern and not pattern_ok:
            self.last_reject_reason = "bottom_pattern_not_confirmed"
            return None

        pattern_text = pattern_name or "basic_recovery"
        detail_text = ""
        daily_text = daily_pattern_name if daily_ok else "daily_not_required"
        daily_detail_text = ""
        if daily_details:
            daily_detail_text = " | " + " | ".join(
                f"{key}={value:.2f}" if isinstance(value, float) else f"{key}={value}"
                for key, value in daily_details.items()
            )
        if pattern_details:
            detail_text = " | " + " | ".join(
                f"{key}={value:.2f}" if isinstance(value, float) else f"{key}={value}"
                for key, value in pattern_details.items()
            )

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=self.default_qty,
            reason=(
                "bottom_reversal_entry"
                f" | daily={daily_text}"
                f" | pattern={pattern_text}"
                f" | low={intraday_low:.0f}"
                f" | high={intraday_high:.0f}"
                f" | recovery={recovery_from_low_pct:.2f}"
                f" | pullback={pullback_from_high_pct:.2f}"
                f" | low_age={low_age_ticks}"
                f" | last_mom={last_momentum_pct:.2f}"
                f" | chg={price_change_pct:.2f}"
                f" | vr={volume_ratio:.2f}"
                f" | strength={trade_strength:.1f}"
                f"{daily_detail_text}"
                f"{detail_text}"
            ),
            price=price,
            order_type=OrderType.MARKET,
            ts=ts,
        )

    def mark_entry(self, symbol: str, ts):
        if not isinstance(ts, datetime):
            ts = datetime.now()
        self.last_entry_at[str(symbol).strip()] = ts
