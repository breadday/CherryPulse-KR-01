#core/risk_manager.py
 
from core.models import Signal, Side
from core.portfolio import Portfolio


class RiskManager:
    def __init__(
        self,
        max_positions: int = 3,
        max_order_value: float = 1_000_000,
        daily_loss_limit: float = -300_000,
    ):
        self.max_positions = max_positions
        self.max_order_value = max_order_value
        self.daily_loss_limit = daily_loss_limit

    def can_trade(self, signal: Signal, portfolio: Portfolio) -> tuple[bool, str]:
        if portfolio.realized_pnl <= self.daily_loss_limit:
            return False, "일일 손실 제한 초과"

        est_price = signal.price if signal.price else 0
        est_value = est_price * signal.qty if est_price > 0 else 0

        if est_value > self.max_order_value:
            return False, "주문 금액 한도 초과"

        if signal.side == Side.BUY:
            if not portfolio.has_position(signal.symbol):
                if portfolio.total_positions() >= self.max_positions:
                    return False, "최대 보유 종목 수 초과"

        if signal.side == Side.SELL:
            pos = portfolio.get_position(signal.symbol)
            if pos.qty <= 0:
                return False, "매도 가능한 보유 수량 없음"

        return True, "OK"