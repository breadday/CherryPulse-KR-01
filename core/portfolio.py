from dataclasses import dataclass
from typing import Dict
from core.models import Fill, Side


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_price: float = 0.0


class Portfolio:
    def __init__(self, initial_cash: float):
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.realized_pnl = 0.0

    def get_position(self, symbol: str) -> Position:
        return self.positions.get(symbol, Position(symbol=symbol))

    def has_position(self, symbol: str) -> bool:
        return self.get_position(symbol).qty > 0

    def update_fill(self, fill: Fill):
        pos = self.positions.get(fill.symbol, Position(symbol=fill.symbol))

        if fill.side == Side.BUY:
            total_cost = (pos.avg_price * pos.qty) + (fill.fill_price * fill.fill_qty)
            new_qty = pos.qty + fill.fill_qty
            pos.avg_price = total_cost / new_qty if new_qty > 0 else 0.0
            pos.qty = new_qty
            self.cash -= fill.fill_price * fill.fill_qty

        elif fill.side == Side.SELL:
            if pos.qty <= 0:
                return

            sell_qty = min(fill.fill_qty, pos.qty)
            pnl = (fill.fill_price - pos.avg_price) * sell_qty
            self.realized_pnl += pnl
            pos.qty -= sell_qty
            self.cash += fill.fill_price * sell_qty

            if pos.qty == 0:
                pos.avg_price = 0.0

        self.positions[fill.symbol] = pos

    def total_positions(self) -> int:
        return sum(1 for _, pos in self.positions.items() if pos.qty > 0)