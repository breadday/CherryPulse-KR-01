# strategy/momentum_intraday.py

from datetime import datetime, timedelta
from core.models import Signal, Side, OrderType


class MomentumIntradayStrategy:

    def __init__(self, config=None):
        self.config = config or {}

        # -------------------------
        # 진입 조건
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

        self.last_entry_time = {}

        # -------------------------
        # 1틱 확인 진입용
        # -------------------------
        # 첫 돌파 틱은 바로 안 사고, 후보만 저장
        # 다음 틱에서 조건이 유지되면 진입
        self.pending_entry = {}

        # 엔진 로그용 마지막 차단 사유
        self.last_block_reason = {}

    # -------------------------
    # 내부 유틸
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
            holding_count = sum(1 for p in portfolio.positions.values() if getattr(p, "qty", 0) > 0)
            if holding_count >= self.max_positions:
                return False, "max_positions"

        if trade_strength < self.min_trade_strength:
            return False, "trade_strength"

        if price_change_pct < self.min_price_change_pct:
            return False, "price_change_pct"

        if volume_ratio < self.min_volume_ratio:
            return False, "volume_ratio"

        return True, "ok"

    # -------------------------
    # 진입 시그널
    # -------------------------
    def generate_signal(self, tick, portfolio):
        symbol = tick.symbol
        price = tick.price

        # 이미 보유 중이면 진입 후보 제거
        pos = portfolio.get_position(symbol)
        if pos.qty > 0:
            self._clear_pending_entry(symbol)
            self._set_block_reason(symbol, "already_holding")
            return None

        market_data = self._build_market_data(tick)
        now = market_data["timestamp"]

        # 공통 진입 필터 체크
        ok, reason = self._check_common_entry_filters(symbol, market_data, portfolio)
        if not ok:
            self._clear_pending_entry(symbol)
            self._set_block_reason(symbol, reason)
            return None

        # -------------------------
        # 1틱 확인 로직
        # -------------------------
        pending = self.pending_entry.get(symbol)

        # 아직 후보가 없으면 이번 틱은 "관찰만"
        if pending is None:
            self.pending_entry[symbol] = {
                "price": price,
                "price_change_pct": market_data["price_change_pct"],
                "trade_strength": market_data["trade_strength"],
                "volume_ratio": market_data["volume_ratio"],
                "timestamp": now,
            }
            self._set_block_reason(symbol, "wait_1tick_confirm")
            return None

        # 후보가 있으면 다음 틱에서 확인
        candidate_price = pending.get("price", 0)

        # 핵심:
        # 다음 틱에서 가격이 후보 틱보다 밀리면 가짜 돌파로 보고 취소
        if price < candidate_price:
            self._clear_pending_entry(symbol)
            self._set_block_reason(symbol, "confirm_fail_price_drop")
            return None

        # 다음 틱에서도 기본 조건 유지되면 진입
        qty = 1
        self._clear_pending_entry(symbol)

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=qty,
            price=0,
            order_type=OrderType.MARKET,
            reason=(
                "momentum_entry:"
                f"1tick_confirm_ok:"
                f"chg={market_data['price_change_pct']:.2f}:"
                f"strength={market_data['trade_strength']:.1f}:"
                f"vr={market_data['volume_ratio']:.2f}"
            ),
        )

    # -------------------------
    # 기존 호환용
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
                "pnl_pct": pnl_pct
            }

        # 부분익절
        if (not position.get("partial_taken", False)) and pnl_pct >= self.partial_take_profit_pct:
            return {
                "action": "PARTIAL_SELL",
                "reason": "partial_take_profit",
                "ratio": self.partial_take_profit_ratio,
                "pnl_pct": pnl_pct
            }

        # 고정 익절
        if pnl_pct >= self.take_profit_pct:
            return {
                "action": "FULL_SELL",
                "reason": "take_profit",
                "pnl_pct": pnl_pct
            }

        # 트레일링
        if highest_return_pct >= self.trailing_start_pct:
            drawdown_from_peak = highest_return_pct - pnl_pct
            if drawdown_from_peak >= self.trailing_gap_pct:
                return {
                    "action": "FULL_SELL",
                    "reason": "trailing_stop",
                    "pnl_pct": pnl_pct,
                    "peak_pct": highest_return_pct
                }

        return None