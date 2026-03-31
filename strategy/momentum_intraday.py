# strategy/momentum_intraday.py

from datetime import datetime, timedelta
from core.models import Signal, Side, OrderType

def generate_signal(self, tick, portfolio):
    """
    tick: TickData
    portfolio: Portfolio
    """

    symbol = tick.symbol
    price = tick.price

    # 이미 보유 중이면 진입 안함
    pos = portfolio.get_position(symbol)
    if pos.qty > 0:
        return None

    # market_data 구성 (전략 입력용)
    market_data = {
        "price": price,
        "price_change_pct": getattr(tick, "price_change_pct", 0.0),
        "trade_strength": getattr(tick, "trade_strength", 0.0),
        "volume_ratio": getattr(tick, "volume_ratio", 1.0),
        "timestamp": getattr(tick, "ts", None),
    }

    # 진입 조건 체크
    ok, reason = self.can_enter(symbol, market_data, portfolio)
    if not ok:
        return None

    # 수량 결정 (기본: 1주 테스트)
    qty = 1

    return Signal(
        symbol=symbol,
        side=Side.BUY,
        qty=qty,
        price=0,
        order_type=OrderType.MARKET,
        reason=f"momentum_entry:{reason}",
    )

class MomentumIntradayStrategy:
    
    def __init__(self, config=None):
        self.config = config or {}

        # 진입 조건
        self.min_trade_strength = self.config.get("min_trade_strength", 120)
        self.min_price_change_pct = self.config.get("min_price_change_pct", 0.5)
        self.min_volume_ratio = self.config.get("min_volume_ratio", 1.5)
        self.max_positions = self.config.get("max_positions", 3)

        # 청산 조건
        self.stop_loss_pct = self.config.get("stop_loss_pct", -2.0)
        self.take_profit_pct = self.config.get("take_profit_pct", 3.0)
        self.partial_take_profit_pct = self.config.get("partial_take_profit_pct", 2.0)
        self.partial_take_profit_ratio = self.config.get("partial_take_profit_ratio", 0.5)
        self.trailing_start_pct = self.config.get("trailing_start_pct", 1.5)
        self.trailing_gap_pct = self.config.get("trailing_gap_pct", 1.0)

        # 재진입 / 백테스트용
        self.entry_cooldown_sec = self.config.get("entry_cooldown_sec", 30)
        self.allow_reentry = self.config.get("allow_reentry", False)

        self.last_entry_time = {}

    def generate_signal(self, tick, portfolio):
        symbol = tick.symbol
        price = tick.price

        # 이미 보유 중이면 진입 안함
        pos = portfolio.get_position(symbol)
        if pos.qty > 0:
            return None

        # market_data 구성
        market_data = {
            "price": price,
            "price_change_pct": getattr(tick, "price_change_pct", 0.0),
            "trade_strength": getattr(tick, "trade_strength", 0.0),
            "volume_ratio": getattr(tick, "volume_ratio", 1.0),
            "timestamp": getattr(tick, "ts", None),
        }

        ok, reason = self.can_enter(symbol, market_data, portfolio)
        if not ok:
            return None

        # 테스트용 1주
        qty = 1

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            qty=qty,
            price=0,
            order_type=OrderType.MARKET,
            reason=f"momentum_entry:{reason}",
        )
    
    def can_enter(self, symbol, market_data, portfolio=None):
        """
        진입 가능 여부 판단
        market_data 예시:
        {
            "price": 70500,
            "price_change_pct": 1.2,
            "trade_strength": 145,
            "volume_ratio": 2.3,
            "timestamp": datetime(...)
        }
        """
        price_change_pct = market_data.get("price_change_pct", 0.0)
        trade_strength = market_data.get("trade_strength", 0.0)
        volume_ratio = market_data.get("volume_ratio", 0.0)
        now = market_data.get("timestamp", datetime.now())

        # 재진입 제한
        if symbol in self.last_entry_time:
            diff = now - self.last_entry_time[symbol]
            if diff < timedelta(seconds=self.entry_cooldown_sec):
                return False, "entry_cooldown"

        # 포트폴리오 최대 보유 수 제한
        if portfolio is not None:
            if len(portfolio.positions) >= self.max_positions:
                return False, "max_positions"

        if trade_strength < self.min_trade_strength:
            return False, "trade_strength"

        if price_change_pct < self.min_price_change_pct:
            return False, "price_change_pct"

        if volume_ratio < self.min_volume_ratio:
            return False, "volume_ratio"

        return True, "ok"

    def mark_entry(self, symbol, timestamp=None):
        self.last_entry_time[symbol] = timestamp or datetime.now()

    def should_exit(self, position, market_data):
        """
        청산 조건 판단
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