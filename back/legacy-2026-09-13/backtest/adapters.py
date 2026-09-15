# backtest/adapters.py   -- 백테스트 runner 가 CSV 바 형대를 받을수 있게 보조 변환기 추가

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BacktestTick:
    code: str
    price: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    dt: Any