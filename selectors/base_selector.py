from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable


class BaseSelector(ABC):
    @abstractmethod
    def select(self) -> list[str]:
        raise NotImplementedError

    def matches_tick(self, tick) -> tuple[bool, str]:
        return True, ""

    def _resolve_universe_provider(self):
        config = getattr(self, "config", {}) or {}
        provider = config.get("universe_provider")
        return provider if callable(provider) else None

    def _matches_strategy_universe(self, symbol: str, universe_name: str) -> tuple[bool, str]:
        provider = self._resolve_universe_provider()
        if provider is None:
            return True, ""
        try:
            allowed = bool(provider(universe_name, symbol))
        except Exception:
            return True, ""
        if allowed:
            return True, ""
        return False, f"selector_universe_miss:{universe_name}"


class CodeUniverse:
    def __init__(self):
        self.active_codes: set[str] = set()

    def replace(self, codes: Iterable[str]) -> list[str]:
        clean = sorted({str(x).strip() for x in codes if str(x).strip()})
        self.active_codes.clear()
        self.active_codes.update(clean)
        return clean

    def add(self, code: str) -> None:
        symbol = str(code).strip()
        if symbol:
            self.active_codes.add(symbol)

    def discard(self, code: str) -> None:
        symbol = str(code).strip()
        if symbol:
            self.active_codes.discard(symbol)

    def contains(self, code: str) -> bool:
        return str(code).strip() in self.active_codes

    def count(self) -> int:
        return len(self.active_codes)

    def snapshot(self) -> list[str]:
        return sorted(self.active_codes)
