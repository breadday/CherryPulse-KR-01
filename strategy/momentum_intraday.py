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
        self.take_profit_pct = self.config.get("take_profit_pct", 3.0)
        self.partial_take_profit_pct = self.config.get("partial_take_profit_pct", 2.0)
        self.partial_take_profit_ratio = self.config.get("partial_take_profit_ratio", 0.5)
        self.trailing_start_pct = self.config.get("trailing_start_pct", 1.5)
        self.trailing_gap_pct = self.config.get("trailing_gap_pct", 1.0)

        # -------------------------
        # 재진입 / 백테스트용
        # -------------------------
        self.entry_cooldown_sec = self.config.get("entry_cooldown_sec", 30)
        self.allow_reentry = self.config.get("allow_reentry", False)

        # -------------------------
        # 최종 튜닝 파라미터
        # config 수정 없이 기본값으로 동작
        # -------------------------
        # 2틱 유지 확인용
        self.confirm_ticks_required = self.config.get("confirm_ticks_required", 2)

        # 후보 대비 거래강도 유지 비율
        self.confirm_strength_ratio = self.config.get("confirm_strength_ratio", 0.95)

        # 확인틱 최소 등락률
        self.min_confirm_price_change_pct = self.config.get(
            "min_confirm_price_change_pct",
            self.min_price_change_pct
        )

        # 강한 돌파는 즉시 진입 허용
        self.instant_entry_trade_strength = self.config.get("instant_entry_trade_strength", 180)
        self.instant_entry_price_change_pct = self.config.get("instant_entry_price_change_pct", 2.0)
        self.instant_entry_volume_ratio = self.config.get("instant_entry_volume_ratio", 1.8)

        # 과열 추격 제한
        self.max_chase_price_change_pct = self.config.get("max_chase_price_change_pct", 6.0)

        # -------------------------
        # 내부 상태
        # -------------------------
        self.last_entry_time = {}
        self.pending_entry = {}
        self.last_block_reason = {}
        self.last_tick_price = {}

    # -------------------------
    # 공통 유틸
    # -------------------------
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

        # 재진입 제한
        if symbol in self.last_entry_time:
            diff = now - self.last_entry_time[symbol]
            if diff < timedelta(seconds=self.entry_cooldown_sec):
                return False, "entry_cooldown"

        # 포트폴리오 최대 보유 수 제한
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

    # -------------------------
    # 진입 시그널
    # -------------------------
    def generate_signal(self, tick, portfolio):
        symbol = tick.symbol
        price = tick.price

        market_data = self._build_market_data(tick)
        now = market_data["timestamp"]
        price_change_pct = market_data["price_change_pct"]
        trade_strength = market_data["trade_strength"]
        volume_ratio = market_data["volume_ratio"]

        prev_price = self.last_tick_price.get(symbol)

        # 이미 보유 중이면 진입 후보 제거
        pos = portfolio.get_position(symbol)
        if pos.qty > 0:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "already_holding")
            return None

        # 공통 필터
        ok, reason = self._check_common_entry_filters(symbol, market_data, portfolio)
        if not ok:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, reason)
            return None

        # 과열 추격 차단
        if price_change_pct > self.max_chase_price_change_pct:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "overheat_chase_block")
            return None

        # 직전 틱보다 밀리면 신규 진입 금지
        if prev_price is not None and price < prev_price:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "price_below_prev_tick")
            return None

        # 강한 돌파는 즉시 진입 허용 (단, 과열은 위에서 차단)
        if self._is_instant_entry_condition(market_data):
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price

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

        # -------------------------
        # 1차 후보 등록
        # -------------------------
        if pending is None:
            if prev_price is not None and price <= prev_price:
                self.last_tick_price[symbol] = price
                self._set_block_reason(symbol, "candidate_not_rising")
                return None

            self.pending_entry[symbol] = {
                "price": price,
                "price_change_pct": price_change_pct,
                "trade_strength": trade_strength,
                "volume_ratio": volume_ratio,
                "timestamp": now,
                "confirm_count": 1,
            }
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "wait_confirm_tick_1")
            return None

        # -------------------------
        # 후보 유지 확인
        # -------------------------
        candidate_price = pending.get("price", 0)
        candidate_strength = pending.get("trade_strength", 0.0)
        candidate_price_change_pct = pending.get("price_change_pct", 0.0)
        confirm_count = int(pending.get("confirm_count", 1))

        # 가격 밀리면 후보 취소
        if price < candidate_price:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_price_drop")
            return None

        # 등락률 약해지면 취소
        if price_change_pct < self.min_confirm_price_change_pct:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_price_change")
            return None

        # 거래강도 유지 실패면 취소
        required_strength = max(
            self.min_trade_strength,
            candidate_strength * self.confirm_strength_ratio
        )
        if trade_strength < required_strength:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_strength_drop")
            return None

        # 거래량 유지 실패
        if volume_ratio < self.min_volume_ratio:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_volume_ratio")
            return None

        # 모멘텀 약화 취소
        if price_change_pct < candidate_price_change_pct:
            self._clear_pending_entry(symbol)
            self.last_tick_price[symbol] = price
            self._set_block_reason(symbol, "confirm_fail_momentum_weaken")
            return None

        # 유지 확인 카운트 증가
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

        # 최종 진입
        self._clear_pending_entry(symbol)
        self.last_tick_price[symbol] = price

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=1,
            price=0,
            order_type=OrderType.MARKET,
            reason=(
                "momentum_entry:"
                "confirm_2tick_ok:"
                f"chg={price_change_pct:.2f}:"
                f"prev_chg={candidate_price_change_pct:.2f}:"
                f"strength={trade_strength:.1f}:"
                f"prev_strength={candidate_strength:.1f}:"
                f"vr={volume_ratio:.2f}"
            ),
        )

    # -------------------------
    # 엔진 호환용
    # -------------------------
    def can_enter(self, symbol, market_data, portfolio=None):
        return self._check_common_entry_filters(symbol, market_data, portfolio)

    def mark_entry(self, symbol, timestamp=None):
        self.last_entry_time[symbol] = self._now(timestamp)
        self._clear_pending_entry(symbol)

    # -------------------------
    # 청산 조건
    # -------------------------
    def should_exit(self, position, market_data):
        """
        position 예시:
        {
            "symbol": "005930",
            "avg_price": 70000,
            "qty": 10,
            "highest_return_pct": 0.0,
            "partial_taken": False,
        }
        """
        current_price = market_data.get("price")
        if not current_price or position["avg_price"] <= 0:
            return None

        avg_price = position["avg_price"]
        pnl_pct = ((current_price - avg_price) / avg_price) * 100.0

        # 최고 수익률 갱신
        highest_return_pct = position.get("highest_return_pct", pnl_pct)
        if pnl_pct > highest_return_pct:
            highest_return_pct = pnl_pct
            position["highest_return_pct"] = highest_return_pct

        # 손절
        if pnl_pct <= self.stop_loss_pct:
            return {
                "action": "FULL_SELL",
                "reason": "stop_loss",
                "pnl_pct": pnl_pct,
            }

        # 부분 익절
        if (not position.get("partial_taken", False)) and pnl_pct >= self.partial_take_profit_pct:
            return {
                "action": "PARTIAL_SELL",
                "reason": "partial_take_profit",
                "ratio": self.partial_take_profit_ratio,
                "pnl_pct": pnl_pct,
            }

        # 고정 익절
        if pnl_pct >= self.take_profit_pct:
            return {
                "action": "FULL_SELL",
                "reason": "take_profit",
                "pnl_pct": pnl_pct,
            }

        # 트레일링 스탑
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
