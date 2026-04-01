# backtest/csv_feed.py

from __future__ import annotations

from typing import List

from backtest.runner import BacktestTick
from data.csv_loader import BarData


def bars_to_ticks(
    bars: List[BarData],
    *,
    default_trade_strength: float = 150.0,
    volume_window: int = 20,
) -> List[BacktestTick]:
    ticks: List[BacktestTick] = []
    prev_close: float | None = None
    volume_history: List[float] = []

    for bar in bars:
        if prev_close is not None and prev_close > 0:
            price_change_pct = ((bar.close - prev_close) / prev_close) * 100.0
        else:
            price_change_pct = 0.0

        recent_volumes = volume_history[-volume_window:]
        avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else bar.volume
        volume_ratio = (bar.volume / avg_volume) if avg_volume > 0 else 1.0

        ticks.append(
            BacktestTick(
                symbol=bar.code,
                price=float(bar.close),
                volume=float(bar.volume),
                ts=bar.dt,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                price_change_pct=float(price_change_pct),
                trade_strength=float(default_trade_strength),
                volume_ratio=float(volume_ratio),
            )
        )

        prev_close = bar.close
        volume_history.append(bar.volume)

    return ticks