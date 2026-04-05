# strategy/momentum_intraday.py
# 최종 밸런스 완성판 전략
#
# 목표
# 1) case1 회복
# 2) case2 재악화 최소화
# 3) case3 손실 더 빠르게 축소
# 4) case4 유지
#
# 핵심 변경
# - confirm_ticks_required: 2 유지
# - instant_entry_trade_strength: 180 -> 175
# - instant_entry_price_change_pct: 1.8 -> 1.7
# - instant_entry_volume_ratio: 1.8 -> 1.7
# - confirm_strength_ratio: 0.95 유지
# - confirm_price_change_keep_ratio: 0.90 유지
# - early_exit_max_hold_ticks: 3 -> 2
# - early_exit_price_drop_pct: -0.1 -> -0.05
# - early_exit_strength_keep_ratio: 0.90 유지
# - early_peak_retrace_pct: 0.7 -> 0.5
#
# 적용 후 실행
#   python run_replay_cases_final.py --repeat 5
#   python analyze_replay_results.py --latest

from datetime import datetime, timedelta
from core.models import Signal, Side, OrderType


class MomentumIntradayStrategy:
    def __init__(self, config=None):
        self.config = config or {}

        # -------------------------
        # 기본 진입 조건
        # -------------------------
        self.min_trade_strength = self.config.get("min_trade_strength", 120)
        self.min_price_change_pct = self.config.get("min_price_change_pct", 0.5)
        self.min_volume_ratio = self.config.get("min_volume_ratio", 1.5)
        self.max_positions = self.config.get("max_positions", 3)

        # -------------------------
        # 청산 조건
        # -------------------------
        self.stop_loss_pct = self.config.get("stop_loss_pct", -2.0)
        self.take_profit_pct = self.config.get("take_profit_pct", 4.0)
        self.partial_take_profit_pct = self.config.get("partial_take_profit_pct", 1.5)
        self.partial_take_profit_ratio = self.config.get("partial_take_profit_ratio", 0.5)
        self.trailing_start_pct = self.config.get("trailing_start_pct", 2.0)
        self.trailing_gap_pct = self.config.get("trailing_gap_pct", 1.0)

        # -------------------------
        # 재진입 / 백테스트용
        # -------------------------
        self.entry_cooldown_sec = self.config.get("entry_cooldown_sec", 30)
        self.allow_reentry = self.config.get("allow_reentry", False)

        # -------------------------
        # 진입 최적화 파라미터
        # -------------------------
        self.confirm_ticks_required = self.config.get("confirm_ticks_required", 2)
        self.confirm_strength_ratio = self.config.get("confirm_strength_ratio", 0.95)
        self.min_confirm_price_change_pct = self.config.get(
            "min_confirm_price_change_pct",
            self.min_price_change_pct
        )

        self.instant_entry_trade_strength = self.config.get("instant_entry_trade_strength", 175)
        self.instant_entry_price_change_pct = self.config.get("instant_entry_price_change_pct", 1.7)
        self.instant_entry_volume_ratio = self.config.get("instant_entry_volume_ratio", 1.7)

        self.max_chase_price_change_pct = self.config.get("max_chase_price_change_pct", 7.0)
        self.confirm_price_change_keep_ratio = self.config.get("confirm_price_change_keep_ratio", 0.90)
        self.max_prev_tick_pullback_pct = self.config.get("max_prev_tick_pullback_pct", 0.2)

        # -------------------------
        # 조기 실패 청산 파라미터
        # -------------------------
        self.early_exit_enabled = self.config.get("early_exit_enabled", True)
        self.early_exit_max_hold_ticks = self.config.get("early_exit_max_hold_ticks", 2)
        self.early_exit_price_drop_pct = self.config.get("early_exit_price_drop_pct", -0.05)
        self.early_exit_strength_keep_ratio = self.config.get("early_exit_strength_keep_ratio", 0.90)
        self.early_exit_min_price_change_keep_ratio = self.config.get(
            "early_exit_min_price_change_keep_ratio", 0.75
        )

        self.early_peak_retrace_enabled = self.config.get("early_peak_retrace_enabled", True)
        self.early_peak_retrace_max_hold_ticks = self.config.get("early_peak_retrace_max_hold_ticks", 2)
        self.early_peak_retrace_pct = self.config.get("early_peak_retrace_pct", 0.5)

        # -------------------------
        # 내부 상태
        # -------------------------
        self.last_entry_time = {}
        self.pending_entry = {}
        self.last_block_reason = {}
        self.last_tick_price = {}
        self.entry_context = {}
        self.tick_seq = {}

    def _now(self, ts=None):
        if ts is None:
            return datetime.now()
        return ts

    def _set_block_reason(self, symbol, reason):
        self.last_block_reason[symbol] = reason

    def get_last_block_reason(self, symbol):
        return self.last_block_reason.get(symbol, "")

    def _clear_pending_entry(self, symbol):
        if symbol in self.pending_entry:
            del self.pending_entry[symbol]

    def _build_market_data(self, tick):
        return {
            "price": tick.price,
            "price_change_pct": getattr(tick, "price_change_pct", 0.0),
            "trade_strength": getattr(tick, "trade_strength", 0.0),
            "volume_ratio": getattr(tick, "volume_ratio", 1.0),
            "timestamp": self._now(getattr(tick, "ts", None)),
        }

    def _check_common_entry_filters(self, symbol, market_data, portfolio=None):
        price_change_pct = market_data.get("price_change_pct", 0.0)
        trade_strength = market_data.get("trade_strength", 0.0)
        volume_ratio = market_data.get("volume_ratio", 0.0)
        now = self._now(market_data.get("timestamp"))

        if symbol in self.last_entry_time:
            diff = now - self.last_entry_time[symbol]
            if diff < timedelta(seconds=self.entry_cooldown_sec):
                return False, "entry_cooldown"

        if portfolio is not None:
            positions = getattr(portfolio, "positions", {})
            holding_count = sum(
                1 for p in positions.values() if getattr(p, "qty", 0) > 0
            )
            if holding_count >= self.max_positions:
                return False, "max_positions"

        if trade_strength < self.min_trade_strength:
            return False, "trade_strength"

        if price_change_pct < self.min_price_change_pct:
            return False, "price_change_pct"

        if volume_ratio < self.min_volume_ratio:
            return False, "volume_ratio"

        return True, "ok"

    def _is_instant_entry_condition(self, market_data):
        return (
            market_data.get("trade_strength", 0.0) >= self.instant_entry_trade_strength
            and market_data.get("price_change_pct", 0.0) >= self.instant_entry_price_change_pct
            and market_data.get("volume_ratio", 0.0) >= self.instant_entry_volume_ratio
            and market_data.get("price_change_pct", 0.0) <= self.max_chase_price_change_pct
        )

    def _is_prev_tick_pullback_too_large(self, prev_price, price):
        if prev_price is None or prev_price <= 0:
            return False
        pullback_pct = ((prev_price - price) / prev_price) * 100.0
        return pullback_pct > self.max_prev_tick_pullback_pct

    def _register_tick(self, symbol):
        self.tick_seq[symbol] = int(self.tick_seq.get(symbol, 0)) + 1
        return self.tick_seq[symbol]

    def generate_signal(self, tick, portfolio):
        symbol = tick.symbol
        price = tick.price

        market_data = self._build_market_data(tick)
        now = market_data["timestamp"]
        price_change_pct = market_data["price_change_pct"]
        trade_strength = market_data["trade_strength"]
        volume_ratio = market_data["volume_ratio"]

        prev_price = self.last_tick_price.get(symbol)
        current_tick_no = self._register_tick(symbol)

        pos = portfolio.get_position(symbol)
        if pos.qty > 0:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "already_holding")
            return None

        ok, reason = self._check_common_entry_filters(symbol, market_data, portfolio)
        if not ok:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, reason)
            return None

        if price_change_pct > self.max_chase_price_change_pct:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "overheat_chase_block")
            return None

        if self._is_prev_tick_pullback_too_large(prev_price, price):
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "prev_tick_pullback_too_large")
            return None

        if self._is_instant_entry_condition(market_data):
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self.entry_context[symbol] = {
                "entry_tick_no": current_tick_no,
                "entry_signal_price": price,
                "entry_signal_strength": trade_strength,
                "entry_signal_price_change_pct": price_change_pct,
                "entry_signal_volume_ratio": volume_ratio,
                "entry_type": "instant_breakout",
                "peak_price_after_entry": price,
            }
            return Signal(
                symbol=symbol,
                side=Side.BUY,
                qty=1,
                price=0,
                order_type=OrderType.MARKET,
                reason=(
                    "momentum_entry:"
                    "instant_breakout_ok:"
                    f"chg={price_change_pct:.2f}:"
                    f"strength={trade_strength:.1f}:"
                    f"vr={volume_ratio:.2f}"
                ),
            )

        pending = self.pending_entry.get(symbol)

        if pending is None:
            self.pending_entry[symbol] = {
                "price": price,
                "price_change_pct": price_change_pct,
                "trade_strength": trade_strength,
                "volume_ratio": volume_ratio,
                "timestamp": now,
                "confirm_count": 0,
            }
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "wait_confirm_tick_0")
            return None

        candidate_price = pending.get("price", 0)
        candidate_strength = pending.get("trade_strength", 0.0)
        candidate_price_change_pct = pending.get("price_change_pct", 0.0)
        confirm_count = int(pending.get("confirm_count", 0))

        if price < candidate_price:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_price_drop")
            return None

        if price_change_pct < self.min_confirm_price_change_pct:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_price_change")
            return None

        required_strength = max(
            self.min_trade_strength,
            candidate_strength * self.confirm_strength_ratio
        )
        if trade_strength < required_strength:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_strength_drop")
            return None

        if volume_ratio < self.min_volume_ratio:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_volume_ratio")
            return None

        min_keep_price_change_pct = candidate_price_change_pct * self.confirm_price_change_keep_ratio
        if price_change_pct < min_keep_price_change_pct:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_momentum_weaken")
            return None

        confirm_count += 1

        if confirm_count < self.confirm_ticks_required:
            pending["confirm_count"] = confirm_count
            pending["price"] = price
            pending["price_change_pct"] = price_change_pct
            pending["trade_strength"] = trade_strength
            pending["volume_ratio"] = volume_ratio
            pending["timestamp"] = now

            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, f"wait_confirm_tick_{confirm_count}")
            return None

        self._clear_pending_entry(symbol)
        self.last_tick_price[symbol] = price
        self.entry_context[symbol] = {
            "entry_tick_no": current_tick_no,
            "entry_signal_price": price,
            "entry_signal_strength": trade_strength,
            "entry_signal_price_change_pct": price_change_pct,
            "entry_signal_volume_ratio": volume_ratio,
            "entry_type": "confirmed_entry",
            "peak_price_after_entry": price,
        }

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=1,
            price=0,
            order_type=OrderType.MARKET,
            reason=(
                "momentum_entry:"
                "optimized_confirm_ok:"
                f"chg={price_change_pct:.2f}:"
                f"prev_chg={candidate_price_change_pct:.2f}:"
                f"strength={trade_strength:.1f}:"
                f"prev_strength={candidate_strength:.1f}:"
                f"vr={volume_ratio:.2f}"
            ),
        )

    def can_enter(self, symbol, market_data, portfolio=None):
        return self._check_common_entry_filters(symbol, market_data, portfolio)

    def mark_entry(self, symbol, timestamp=None):
        self.last_entry_time[symbol] = self._now(timestamp)
        self._clear_pending_entry(symbol)

    def should_exit(self, position, market_data):
        current_price = market_data.get("price")
        if not current_price or position["avg_price"] <= 0:
            return None

        symbol = position.get("symbol", "")
        avg_price = position["avg_price"]
        pnl_pct = ((current_price - avg_price) / avg_price) * 100.0

        highest_return_pct = position.get("highest_return_pct", pnl_pct)
        if pnl_pct > highest_return_pct:
            highest_return_pct = pnl_pct
            position["highest_return_pct"] = highest_return_pct

        if self.early_exit_enabled and symbol:
            ctx = self.entry_context.get(symbol)
            if ctx:
                current_tick_no = int(self.tick_seq.get(symbol, 0))
                entry_tick_no = int(ctx.get("entry_tick_no", current_tick_no))
                ticks_from_entry = current_tick_no - entry_tick_no

                signal_strength = float(ctx.get("entry_signal_strength", 0.0))
                signal_price_change_pct = float(ctx.get("entry_signal_price_change_pct", 0.0))
                current_strength = float(market_data.get("trade_strength", 0.0))
                current_price_change_pct = float(market_data.get("price_change_pct", 0.0))

                peak_price_after_entry = float(ctx.get("peak_price_after_entry", current_price))
                if current_price > peak_price_after_entry:
                    peak_price_after_entry = current_price
                    ctx["peak_price_after_entry"] = current_price

                strength_fail = (
                    signal_strength > 0
                    and current_strength < (signal_strength * self.early_exit_strength_keep_ratio)
                )
                momentum_fail = (
                    signal_price_change_pct > 0
                    and current_price_change_pct < (
                        signal_price_change_pct * self.early_exit_min_price_change_keep_ratio
                    )
                )
                price_fail = pnl_pct <= self.early_exit_price_drop_pct

                if ticks_from_entry <= self.early_exit_max_hold_ticks and price_fail and (strength_fail or momentum_fail):
                    return {
                        "action": "FULL_SELL",
                        "reason": "early_failure_exit",
                        "pnl_pct": pnl_pct,
                    }

                if self.early_peak_retrace_enabled and ticks_from_entry <= self.early_peak_retrace_max_hold_ticks:
                    if peak_price_after_entry > 0:
                        retrace_pct = ((peak_price_after_entry - current_price) / peak_price_after_entry) * 100.0
                        if retrace_pct >= self.early_peak_retrace_pct and (strength_fail or momentum_fail):
                            return {
                                "action": "FULL_SELL",
                                "reason": "early_peak_retrace_exit",
                                "pnl_pct": pnl_pct,
                            }

        if pnl_pct <= self.stop_loss_pct:
            return {
                "action": "FULL_SELL",
                "reason": "stop_loss",
                "pnl_pct": pnl_pct,
            }

        if (not position.get("partial_taken", False)) and pnl_pct >= self.partial_take_profit_pct:
            return {
                "action": "PARTIAL_SELL",
                "reason": "partial_take_profit",
                "ratio": self.partial_take_profit_ratio,
                "pnl_pct": pnl_pct,
            }

        if pnl_pct >= self.take_profit_pct:
            return {
                "action": "FULL_SELL",
                "reason": "take_profit",
                "pnl_pct": pnl_pct,
            }

        if highest_return_pct >= self.trailing_start_pct:
            drawdown_from_peak = highest_return_pct - pnl_pct
            if drawdown_from_peak >= self.trailing_gap_pct:
                return {
                    "action": "FULL_SELL",
                    "reason": "trailing_stop",
                    "pnl_pct": pnl_pct,
                    "peak_pct": highest_return_pct,
                }

        return None
