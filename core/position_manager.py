# core/position_manager.py
from dataclasses import dataclass, field
from typing import Dict, Optional
import time


@dataclass
class Position:
    code: str
    qty: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    highest_price: float = 0.0
    entry_time: float = field(default_factory=time.time)

    def update_on_buy_fill(self, fill_qty: int, fill_price: float):
        if fill_qty <= 0:
            return
        total_cost = (self.avg_price * self.qty) + (fill_price * fill_qty)
        self.qty += fill_qty
        if self.qty > 0:
            self.avg_price = total_cost / self.qty
        self.highest_price = max(self.highest_price, fill_price)

    def update_on_sell_fill(self, fill_qty: int, fill_price: float):
        if fill_qty <= 0 or self.qty <= 0:
            return 0.0

        sell_qty = min(fill_qty, self.qty)
        pnl = (fill_price - self.avg_price) * sell_qty
        self.realized_pnl += pnl
        self.qty -= sell_qty

        if self.qty == 0:
            self.avg_price = 0.0
            self.highest_price = 0.0

        return pnl

    def update_market_price(self, current_price: float):
        if self.qty > 0:
            self.highest_price = max(self.highest_price, current_price)

    def unrealized_pnl_ratio(self, current_price: float) -> float:
        if self.qty <= 0 or self.avg_price <= 0:
            return 0.0
        return (current_price - self.avg_price) / self.avg_price

    def trailing_drawdown_ratio(self, current_price: float) -> float:
        if self.qty <= 0 or self.highest_price <= 0:
            return 0.0
        return (current_price - self.highest_price) / self.highest_price


class PositionManager:
    def __init__(self):
        self.positions: Dict[str, Position] = {}

    def get(self, code: str) -> Optional[Position]:
        return self.positions.get(code)

    def ensure(self, code: str) -> Position:
        if code not in self.positions:
            self.positions[code] = Position(code=code)
        return self.positions[code]

    def on_buy_fill(self, code: str, fill_qty: int, fill_price: float):
        pos = self.ensure(code)
        pos.update_on_buy_fill(fill_qty, fill_price)

    def on_sell_fill(self, code: str, fill_qty: int, fill_price: float) -> float:
        pos = self.ensure(code)
        pnl = pos.update_on_sell_fill(fill_qty, fill_price)
        if pos.qty == 0:
            # 완전 청산 시 필요하면 삭제 가능
            pass
        return pnl

    def update_tick(self, code: str, current_price: float):
        pos = self.ensure(code)
        pos.update_market_price(current_price)

    def has_position(self, code: str) -> bool:
        pos = self.positions.get(code)
        return bool(pos and pos.qty > 0)