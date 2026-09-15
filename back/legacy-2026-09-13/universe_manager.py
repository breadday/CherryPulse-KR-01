from __future__ import annotations

from pathlib import Path
from typing import Iterable

from selectors import CodeUniverse, SnapshotSelector


class UniverseManager:
    def __init__(self, snapshot_path: Path, fallback_condition_name: str, strategy_universe_config: dict | None = None):
        self.snapshot_path = Path(snapshot_path)
        self.snapshot_selector = SnapshotSelector(self.snapshot_path, fallback_condition_name)
        self.strategy_universe_config = strategy_universe_config or {}

        self.snapshot_universe = CodeUniverse()
        self.condition_universe = CodeUniverse()

        self.strategy_names = sorted(self.strategy_universe_config.keys())
        self.strategy_source_universes = {
            strategy_name: {
                "snapshot": CodeUniverse(),
                "condition": CodeUniverse(),
            }
            for strategy_name in self.strategy_names
        }

    def _strategy_uses_source(self, strategy_name: str, source: str) -> bool:
        strategy_cfg = self.strategy_universe_config.get(str(strategy_name or "").strip(), {}) or {}
        if source == "snapshot":
            return bool(strategy_cfg.get("use_snapshot", False))
        if source == "condition":
            return bool(strategy_cfg.get("use_condition", True))
        return False

    def _apply_source_to_strategy_universes(self, source: str, codes: Iterable[str]) -> None:
        clean_codes = sorted({str(code).strip() for code in codes if str(code).strip()})
        for strategy_name in self.strategy_names:
            target = self.strategy_source_universes[strategy_name][source]
            if self._strategy_uses_source(strategy_name, source):
                target.replace(clean_codes)
            else:
                target.replace([])

    def strategy_codes(self, strategy_name: str) -> list[str]:
        strategy_name = str(strategy_name or "").strip()
        source_universes = self.strategy_source_universes.get(strategy_name)
        if not source_universes:
            return []
        merged = set(source_universes["snapshot"].snapshot()) | set(source_universes["condition"].snapshot())
        return sorted(merged)

    def strategy_source_codes(self, strategy_name: str, source: str) -> list[str]:
        strategy_name = str(strategy_name or "").strip()
        source = str(source or "").strip()
        source_universes = self.strategy_source_universes.get(strategy_name)
        if not source_universes or source not in source_universes:
            return []
        return source_universes[source].snapshot()

    def strategy_contains(self, strategy_name: str, code: str) -> bool:
        return str(code).strip() in set(self.strategy_codes(strategy_name))

    def strategy_counts(self) -> dict[str, int]:
        return {strategy_name: len(self.strategy_codes(strategy_name)) for strategy_name in self.strategy_names}

    def snapshot_codes(self) -> list[str]:
        return self.snapshot_universe.snapshot()

    def condition_codes(self) -> list[str]:
        return self.condition_universe.snapshot()

    def all_watch_codes(self) -> list[str]:
        merged = set()
        for strategy_name in self.strategy_names:
            merged.update(self.strategy_codes(strategy_name))
        return sorted(merged)

    def replace_snapshot(self, codes: Iterable[str]) -> list[str]:
        clean_codes = self.snapshot_universe.replace(codes)
        self._apply_source_to_strategy_universes("snapshot", clean_codes)
        return clean_codes

    def replace_snapshot_rows(self, rows: Iterable[dict]) -> list[str]:
        clean_codes = []
        strategy_codes = {strategy_name: [] for strategy_name in self.strategy_names}
        has_strategy_tags = False

        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol", "")).strip()
            if not symbol:
                continue
            clean_codes.append(symbol)

            raw_strategies = row.get("strategies", [])
            if isinstance(raw_strategies, str):
                strategies = [raw_strategies]
            elif isinstance(raw_strategies, list):
                strategies = [str(x).strip() for x in raw_strategies if str(x).strip()]
            else:
                strategies = []

            if strategies:
                has_strategy_tags = True
                for strategy_name in strategies:
                    if strategy_name in strategy_codes and self._strategy_uses_source(strategy_name, "snapshot"):
                        strategy_codes[strategy_name].append(symbol)

        clean_codes = sorted(set(clean_codes))
        self.snapshot_universe.replace(clean_codes)

        if has_strategy_tags:
            for strategy_name in self.strategy_names:
                target = self.strategy_source_universes[strategy_name]["snapshot"]
                target.replace(strategy_codes.get(strategy_name, []))
        else:
            self._apply_source_to_strategy_universes("snapshot", clean_codes)

        return clean_codes

    def replace_condition(self, codes: Iterable[str]) -> list[str]:
        clean_codes = self.condition_universe.replace(codes)
        self._apply_source_to_strategy_universes("condition", clean_codes)
        return clean_codes

    def add_condition(self, code: str) -> bool:
        symbol = str(code).strip()
        already_active = self.condition_universe.contains(symbol)
        self.condition_universe.add(symbol)
        for strategy_name in self.strategy_names:
            if self._strategy_uses_source(strategy_name, "condition"):
                self.strategy_source_universes[strategy_name]["condition"].add(symbol)
        return not already_active

    def remove_condition(self, code: str) -> None:
        symbol = str(code).strip()
        self.condition_universe.discard(symbol)
        for strategy_name in self.strategy_names:
            self.strategy_source_universes[strategy_name]["condition"].discard(symbol)

    def has_snapshot(self, code: str) -> bool:
        return self.snapshot_universe.contains(code)

    def has_condition(self, code: str) -> bool:
        return self.condition_universe.contains(code)

    def should_route(self, code: str, has_position: bool = False, has_open_order: bool = False) -> bool:
        symbol = str(code).strip()
        if any(self.strategy_contains(strategy_name, symbol) for strategy_name in self.strategy_names):
            return True
        if has_position:
            return True
        if has_open_order:
            return True
        return False

    def matches_strategy_universe(self, universe_name: str, code: str) -> bool:
        universe_name = str(universe_name or "").strip()
        symbol = str(code or "").strip()
        if not universe_name or not symbol:
            return False

        if universe_name == "momentum_universe":
            return self.strategy_contains("momentum", symbol)
        if universe_name == "vcp_box_universe":
            return self.strategy_contains("vcp_box", symbol)
        if universe_name == "bottom_reversal_universe":
            return self.strategy_contains("bottom_reversal", symbol)
        if universe_name == "leader_universe":
            return self.strategy_contains("leader_pullback", symbol)
        if universe_name == "close_buy_universe":
            return self.strategy_contains("close_buy", symbol)
        return False

    def load_snapshot(self) -> tuple[dict, list[dict[str, str]], list[str]]:
        payload = self.snapshot_selector.load_payload()
        rows = self.snapshot_selector.extract_rows(payload)
        codes = [row["symbol"] for row in rows]
        clean_codes = self.replace_snapshot_rows(rows)
        return payload, rows, clean_codes

    def resolve_snapshot_condition_name(self, payload: dict) -> str:
        return self.snapshot_selector.resolve_condition_name(payload)

    def resolve_snapshot_generated_at(self, payload: dict) -> str:
        return self.snapshot_selector.resolve_generated_at(payload)
