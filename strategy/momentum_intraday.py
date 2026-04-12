# -*- coding: utf-8 -*-
# strategy/momentum_intraday.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class Signal:
    symbol: str
    side: str
    reason: str = ""

class MomentumIntradayStrategy:
    def __init__(self, config=None):
        self.config = config or {}

        # 완화된 조건 (딱 1~2번 거래용)
        self.min_chg = 0.05     # 기존 0.5 → 0.05
        self.min_vr = 1.5       # 기존 3 → 1.5
        self.min_strength = 0.0 # 기존 100 → 제거

    def on_tick(self, tick) -> Optional[Signal]:
        try:
            chg = float(getattr(tick, "chg", 0.0) or 0.0)
            vr = float(getattr(tick, "vr", 0.0) or 0.0)
            strength = float(getattr(tick, "strength", 0.0) or 0.0)
            symbol = str(getattr(tick, "symbol", "")).strip()
        except Exception:
            return None

        if not symbol:
            return None

        # 조건 완화 핵심 3개
        if chg < self.min_chg:
            return None

        if vr < self.min_vr:
            return None

        if strength < self.min_strength:
            return None

        return Signal(symbol=symbol, side="BUY", reason="relaxed_entry")
