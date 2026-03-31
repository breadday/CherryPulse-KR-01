# backtest/runner.py  백테스트 러너

from dataclasses import dataclass
from typing import Dict, List, Optional

from backtest.metrics import summarize_result
from strategy.momentum_intraday import MomentumIntradayStrategy


@dataclass
class BacktestTick:
    symbol: str
    price: float
    volume: float
    ts: object

    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0

    price_change_pct: float = 0.0
    trade_strength: float = 0.0
    volume_ratio: float = 1.0


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_price: float = 0.0
    highest_return_pct: float = 0.0
    partial_taken: bool = False


class SimplePortfolio:
    def __init__(self, initial_cash: float):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.realized_pnl = 0.0
        self.positions: Dict[str, Position] = {}

    def get_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def market_value(self, price_map: Dict[str, int]) -> float:
        total = self.cash
        for symbol, pos in self.positions.items():
            if pos.qty > 0:
                total += pos.qty * price_map.get(symbol, int(pos.avg_price))
        return total

    def buy(self, symbol: str, qty: int, price: float):
        amount = qty * price
        if qty <= 0 or self.cash < amount:
            return False

        pos = self.get_position(symbol)

        new_qty = pos.qty + qty
        if new_qty <= 0:
            return False

        pos.avg_price = ((pos.avg_price * pos.qty) + amount) / new_qty
        pos.qty = new_qty

        self.cash -= amount
        return True

    def sell(self, symbol: str, qty: int, price: float) -> float:
        pos = self.get_position(symbol)

        if qty <= 0 or pos.qty <= 0:
            return 0.0

        sell_qty = min(qty, pos.qty)
        pnl = (price - pos.avg_price) * sell_qty

        self.cash += price * sell_qty
        self.realized_pnl += pnl
        pos.qty -= sell_qty

        if pos.qty == 0:
            pos.avg_price = 0.0
            pos.highest_return_pct = 0.0
            pos.partial_taken = False

        return pnl


class BacktestRunner:
    def __init__(self, strategy_config=None, initial_cash=5_000_000):
        self.strategy = MomentumIntradayStrategy(config=strategy_config or {})
        self.portfolio = SimplePortfolio(initial_cash=initial_cash)
        self.initial_cash = initial_cash

        self.price_map: Dict[str, int] = {}
        self.equity_curve: List[float] = []
        self.trades: List[dict] = []
        self.entry_log: Dict[str, dict] = {}

    def run(self, ticks: List[BacktestTick]):
        for tick in ticks:
            current_price = tick.price if tick.price else tick.close
            self.price_map[tick.symbol] = current_price

            # 1) 청산 먼저 체크
            self._check_exit(tick)

            # 2) 진입 체크
            self._check_entry(tick)

            # 3) 자산곡선 기록
            equity = self.portfolio.market_value(self.price_map)
            self.equity_curve.append(equity)

        final_cash = self.portfolio.market_value(self.price_map)
        result = summarize_result(
            trades=self.trades,
            equity_curve=self.equity_curve,
            initial_cash=self.initial_cash,
            final_cash=final_cash,
        )
        return result

    def _check_entry(self, tick: BacktestTick):
        signal = self.strategy.generate_signal(tick, self.portfolio)
        if signal is None:
            return

        if getattr(signal.side, "value", str(signal.side)) != "BUY":
            return

        qty = int(signal.qty)
        if qty <= 0:
            return

        current_price = tick.price if tick.price else tick.close

        success = self.portfolio.buy(tick.symbol, qty, current_price)
        if not success:
            return

        self.strategy.mark_entry(tick.symbol, tick.ts)

        pos = self.portfolio.get_position(tick.symbol)
        self.entry_log[tick.symbol] = {
            "entry_price": pos.avg_price,
            "entry_ts": tick.ts,
        }

    def _check_exit(self, tick: BacktestTick):
        pos = self.portfolio.get_position(tick.symbol)
        if pos.qty <= 0 or pos.avg_price <= 0:
            return

        current_price = tick.price if tick.price else tick.close

        position_data = {
            "symbol": tick.symbol,
            "avg_price": pos.avg_price,
            "qty": pos.qty,
            "highest_return_pct": pos.highest_return_pct,
            "partial_taken": pos.partial_taken,
        }

        market_data = {
            "price": current_price,
            "timestamp": tick.ts,
        }

        exit_signal = self.strategy.should_exit(position_data, market_data)
        if not exit_signal:
            return

        pos.highest_return_pct = position_data.get("highest_return_pct", pos.highest_return_pct)

        action = exit_signal["action"]

        if action == "PARTIAL_SELL":
            ratio = float(exit_signal.get("ratio", 0.5))
            sell_qty = max(int(pos.qty * ratio), 1)
            pnl = self.portfolio.sell(tick.symbol, sell_qty, current_price)
            pos.partial_taken = True

            self.trades.append({
                "symbol": tick.symbol,
                "entry_price": self.entry_log.get(tick.symbol, {}).get("entry_price", pos.avg_price),
                "exit_price": current_price,
                "qty": sell_qty,
                "pnl": pnl,
                "reason": exit_signal.get("reason", "partial_sell"),
                "entry_ts": self.entry_log.get(tick.symbol, {}).get("entry_ts"),
                "exit_ts": tick.ts,
            })

        elif action == "FULL_SELL":
            sell_qty = pos.qty
            entry_price = self.entry_log.get(tick.symbol, {}).get("entry_price", pos.avg_price)
            entry_ts = self.entry_log.get(tick.symbol, {}).get("entry_ts")

            pnl = self.portfolio.sell(tick.symbol, sell_qty, current_price)

            self.trades.append({
                "symbol": tick.symbol,
                "entry_price": entry_price,
                "exit_price": current_price,
                "qty": sell_qty,
                "pnl": pnl,
                "reason": exit_signal.get("reason", "full_sell"),
                "entry_ts": entry_ts,
                "exit_ts": tick.ts,
            })

            if self.portfolio.get_position(tick.symbol).qty == 0:
                self.entry_log.pop(tick.symbol, None)