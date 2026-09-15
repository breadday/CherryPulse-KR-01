from __future__ import annotations

from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    def __init__(self, config=None):
        self.config = config or {}
        self.last_reject_reason = ""
        self.active_selector_name = ""
        self.active_strategy_name = getattr(self, "strategy_name", self.__class__.__name__)
        self.active_universe_name = ""

    @abstractmethod
    def generate_signal(self, tick, portfolio=None):
        raise NotImplementedError

    def mark_entry(self, symbol: str, ts):
        return None

    def get_active_route_context(self) -> dict[str, str]:
        return {
            "selector_name": str(self.active_selector_name or "").strip(),
            "strategy_name": str(self.active_strategy_name or getattr(self, "strategy_name", self.__class__.__name__)).strip(),
            "universe_name": str(self.active_universe_name or "").strip(),
        }
