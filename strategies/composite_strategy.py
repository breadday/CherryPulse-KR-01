from __future__ import annotations

from datetime import datetime

from selectors import CloseBuySelector, LeaderSelector, MomentumSelector

from .base_strategy import BaseStrategy
from .close_buy_strategy import CloseBuyStrategy
from .leader_pullback_strategy import LeaderPullbackStrategy
from .momentum_strategy import MomentumStrategy


class CompositeIntradayStrategy(BaseStrategy):
    def __init__(self, config=None):
        super().__init__(config=config)
        self.last_reject_details: dict[str, str] = {}
        self.last_entry_at = {}
        self.strategy_pairs: list[tuple[object | None, BaseStrategy]] = []
        self.active_selector_name = ""
        self.active_strategy_name = ""
        self.active_universe_name = ""
        if bool((config or {}).get("enable_momentum_entry", True)):
            self.strategy_pairs.append((MomentumSelector(config=config), MomentumStrategy(config=config)))
        if bool((config or {}).get("enable_leader_pullback_entry", True)):
            self.strategy_pairs.append((LeaderSelector(config=config), LeaderPullbackStrategy(config=config)))
        if bool((config or {}).get("enable_close_buy_entry", False)):
            self.strategy_pairs.append((CloseBuySelector(config=config), CloseBuyStrategy(config=config)))

    def _strategy_runtime_enabled(self, strategy_name: str) -> bool:
        runtime_cfg = (self.config or {}).get("strategy_runtime_config", {})
        if not isinstance(runtime_cfg, dict):
            return True
        strategy_cfg = runtime_cfg.get(str(strategy_name or "").strip(), {})
        if not isinstance(strategy_cfg, dict):
            return True
        return bool(strategy_cfg.get("enabled", True))

    def _strategy_runtime_cfg(self, strategy_name: str) -> dict:
        runtime_cfg = (self.config or {}).get("strategy_runtime_config", {})
        if not isinstance(runtime_cfg, dict):
            return {}
        strategy_cfg = runtime_cfg.get(str(strategy_name or "").strip(), {})
        return strategy_cfg if isinstance(strategy_cfg, dict) else {}

    def _strategy_time_allowed(self, strategy_name: str, tick) -> tuple[bool, str]:
        strategy_cfg = self._strategy_runtime_cfg(strategy_name)
        start_hhmm = str(strategy_cfg.get("start_hhmm", "") or "").strip()
        end_hhmm = str(strategy_cfg.get("end_hhmm", "") or "").strip()
        if not start_hhmm and not end_hhmm:
            return True, ""

        ts = getattr(tick, "ts", None)
        if isinstance(ts, datetime):
            now_hhmm = ts.strftime("%H:%M")
        else:
            now_hhmm = datetime.now().strftime("%H:%M")

        if start_hhmm and now_hhmm < start_hhmm:
            return False, f"time<{start_hhmm}"
        if end_hhmm and now_hhmm > end_hhmm:
            return False, f"time>{end_hhmm}"
        return True, ""

    def generate_signal(self, tick, portfolio=None):
        self.last_reject_reason = ""
        self.last_reject_details = {}
        self.active_selector_name = ""
        self.active_strategy_name = ""
        self.active_universe_name = ""

        for selector, strategy in self.strategy_pairs:
            strategy_name = getattr(strategy, "strategy_name", strategy.__class__.__name__)
            if not self._strategy_runtime_enabled(strategy_name):
                self.last_reject_details[strategy_name] = "strategy_disabled"
                continue
            time_allowed, time_reason = self._strategy_time_allowed(strategy_name, tick)
            if not time_allowed:
                self.last_reject_details[strategy_name] = time_reason
                continue
            if selector is not None and hasattr(selector, "matches_tick"):
                allowed, selector_reason = selector.matches_tick(tick)
                if not allowed:
                    if selector_reason:
                        self.last_reject_details[strategy_name] = selector_reason
                    continue
            signal = strategy.generate_signal(tick, portfolio=portfolio)
            if signal is not None:
                selector_name = getattr(selector, "selector_name", selector.__class__.__name__) if selector is not None else ""
                universe_name = getattr(selector, "universe_name", selector_name) if selector is not None else ""
                self.active_selector_name = str(selector_name or "").strip()
                self.active_strategy_name = str(strategy_name or "").strip()
                self.active_universe_name = str(universe_name or "").strip()
                setattr(signal, "selector_name", self.active_selector_name)
                setattr(signal, "strategy_name", self.active_strategy_name)
                setattr(signal, "universe_name", self.active_universe_name)
                return signal
            reject_reason = getattr(strategy, "last_reject_reason", "")
            if reject_reason:
                self.last_reject_details[strategy_name] = reject_reason

        if self.last_reject_details:
            ordered = []
            if "momentum" in self.last_reject_details:
                ordered.append(f"momentum:{self.last_reject_details['momentum']}")
            if "leader_pullback" in self.last_reject_details:
                ordered.append(f"leader:{self.last_reject_details['leader_pullback']}")
            if "close_buy" in self.last_reject_details:
                ordered.append(f"close_buy:{self.last_reject_details['close_buy']}")
            for key, value in self.last_reject_details.items():
                if key not in ("momentum", "leader_pullback", "close_buy"):
                    ordered.append(f"{key}:{value}")
            self.last_reject_reason = " | ".join(ordered)
        return None

    def mark_entry(self, symbol: str, ts):
        self.last_entry_at[str(symbol).strip()] = ts
        for _, strategy in self.strategy_pairs:
            if hasattr(strategy, "mark_entry"):
                strategy.mark_entry(symbol, ts)
