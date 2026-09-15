# backtest/runner.py

from __future__ import annotations

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

    def market_value(self, price_map: Dict[str, float]) -> float:
        total = self.cash
        for symbol, pos in self.positions.items():
            if pos.qty > 0:
                total += pos.qty * price_map.get(symbol, pos.avg_price)
        return total

    def buy(self, symbol: str, qty: int, price: float) -> bool:
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
    def __init__(
        self,
        strategy: Optional[MomentumIntradayStrategy] = None,
        strategy_config: Optional[dict] = None,
        initial_cash: float = 5_000_000,
    ):
        self.strategy = strategy or MomentumIntradayStrategy(config=strategy_config or {})
        self.portfolio = SimplePortfolio(initial_cash=initial_cash)
        self.initial_cash = initial_cash

        self.price_map: Dict[str, float] = {}
        self.equity_curve: List[float] = []
        self.trades: List[dict] = []
        self.entry_log: Dict[str, dict] = {}

    def run(self, ticks: List[BacktestTick]):
        if not ticks:
            return summarize_result(
                trades=[],
                equity_curve=[],
                initial_cash=self.initial_cash,
                final_cash=self.initial_cash,
            )

        last_tick_by_symbol: Dict[str, BacktestTick] = {}

        for tick in ticks:
            current_price = tick.price if tick.price else tick.close
            self.price_map[tick.symbol] = current_price
            last_tick_by_symbol[tick.symbol] = tick

            self._check_exit(tick)
            self._check_entry(tick)

            equity = self.portfolio.market_value(self.price_map)
            self.equity_curve.append(equity)

        self._force_close_all(last_tick_by_symbol)

        final_cash = self.portfolio.market_value(self.price_map)
        return summarize_result(
            trades=self.trades,
            equity_curve=self.equity_curve,
            initial_cash=self.initial_cash,
            final_cash=final_cash,
        )

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
        if not self.portfolio.buy(tick.symbol, qty, current_price):
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
        current_return_pct = ((current_price - pos.avg_price) / pos.avg_price) * 100.0
        pos.highest_return_pct = max(pos.highest_return_pct, current_return_pct)

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

    def _force_close_all(self, last_tick_by_symbol: Dict[str, BacktestTick]):
        for symbol, pos in list(self.portfolio.positions.items()):
            if pos.qty <= 0:
                continue

            last_tick = last_tick_by_symbol.get(symbol)
            if last_tick is None:
                continue

            current_price = last_tick.price if last_tick.price else last_tick.close
            sell_qty = pos.qty
            entry_price = self.entry_log.get(symbol, {}).get("entry_price", pos.avg_price)
            entry_ts = self.entry_log.get(symbol, {}).get("entry_ts")

            pnl = self.portfolio.sell(symbol, sell_qty, current_price)

            self.trades.append({
                "symbol": symbol,
                "entry_price": entry_price,
                "exit_price": current_price,
                "qty": sell_qty,
                "pnl": pnl,
                "reason": "force_close_end_of_backtest",
                "entry_ts": entry_ts,
                "exit_ts": last_tick.ts,
            })

            self.entry_log.pop(symbol, None)
            self.price_map[symbol] = current_price
            self.equity_curve.append(self.portfolio.market_value(self.price_map))