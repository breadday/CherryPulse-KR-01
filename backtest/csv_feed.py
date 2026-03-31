# backtest/csv_feed.py  :  CSV bar -> runner 입력용 tick 리스크 변환

from __future__ import annotations

from typing import List

from data.csv_loader import BarData
from backtest.runner import BacktestTick   # 👈 중요: runner에 있는 Tick 사용


def bars_to_ticks(bars: List[BarData]) -> List[BacktestTick]:
    ticks: List[BacktestTick] = []

    for bar in bars:
        tick = BacktestTick(
            symbol=bar.code,        # 종목코드 매핑
            price=bar.close,        # 현재가 = 종가
            volume=bar.volume,
            ts=bar.dt,              # 시간

            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
        )

        ticks.append(tick)

    return ticks