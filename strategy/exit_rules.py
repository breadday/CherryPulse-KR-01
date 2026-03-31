# strategy/exit_rules.py
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExitSignal:
    should_exit: bool
    reason: str = ""
    ratio: float = 0.0
    qty_ratio: float = 1.0   # 1.0 = 전량, 0.5 = 절반


class ExitRules:
    def __init__(
        self,
        take_profit=0.025,         # +2.5%
        stop_loss=-0.015,          # -1.5%
        trailing_start=0.02,       # +2.0% 이상부터 트레일링 시작
        trailing_backoff=-0.01,    # 고점 대비 -1.0% 밀리면 청산
        partial_take_profit=0.015  # +1.5%에서 절반 익절
    ):
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.trailing_start = trailing_start
        self.trailing_backoff = trailing_backoff
        self.partial_take_profit = partial_take_profit

    def evaluate(self, position, current_price: float) -> Optional[ExitSignal]:
        if not position or position.qty <= 0 or position.avg_price <= 0:
            return None

        pnl_ratio = position.unrealized_pnl_ratio(current_price)
        drawdown_from_high = position.trailing_drawdown_ratio(current_price)

        # 1차 부분 익절
        if pnl_ratio >= self.partial_take_profit and position.qty >= 2:
            return ExitSignal(
                should_exit=True,
                reason="PARTIAL_TP",
                ratio=pnl_ratio,
                qty_ratio=0.5
            )

        # 전량 익절
        if pnl_ratio >= self.take_profit:
            return ExitSignal(
                should_exit=True,
                reason="TAKE_PROFIT",
                ratio=pnl_ratio,
                qty_ratio=1.0
            )

        # 전량 손절
        if pnl_ratio <= self.stop_loss:
            return ExitSignal(
                should_exit=True,
                reason="STOP_LOSS",
                ratio=pnl_ratio,
                qty_ratio=1.0
            )

        # 트레일링 스탑
        if pnl_ratio >= self.trailing_start and drawdown_from_high <= self.trailing_backoff:
            return ExitSignal(
                should_exit=True,
                reason="TRAILING_STOP",
                ratio=pnl_ratio,
                qty_ratio=1.0
            )

        return ExitSignal(should_exit=False)