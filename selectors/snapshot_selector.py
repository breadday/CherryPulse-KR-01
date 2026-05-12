from __future__ import annotations

import json
from pathlib import Path

from .base_selector import BaseSelector


class SnapshotSelector(BaseSelector):
    def __init__(self, snapshot_path: Path, fallback_condition_name: str):
        self.snapshot_path = Path(snapshot_path)
        self.fallback_condition_name = str(fallback_condition_name).strip()

    def load_payload(self) -> dict:
        return json.loads(self.snapshot_path.read_text(encoding="utf-8"))

    def select(self) -> list[str]:
        payload = self.load_payload()
        rows = self.extract_rows(payload)
        return [row["symbol"] for row in rows]

    def extract_rows(self, payload: dict) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for item in payload.get("codes", []):
            if isinstance(item, dict):
                symbol = str(item.get("symbol", "")).strip()
                name = str(item.get("name", "")).strip()
                raw_strategies = item.get("strategies", [])
            else:
                symbol = str(item).strip()
                name = ""
                raw_strategies = []
            if symbol:
                if isinstance(raw_strategies, str):
                    strategies = [raw_strategies]
                elif isinstance(raw_strategies, list):
                    strategies = [str(x).strip() for x in raw_strategies if str(x).strip()]
                else:
                    strategies = []
                rows.append({"symbol": symbol, "name": name, "strategies": strategies})
        return rows

    def resolve_condition_name(self, payload: dict) -> str:
        return str(payload.get("condition_name", self.fallback_condition_name) or self.fallback_condition_name).strip()

    def resolve_generated_at(self, payload: dict) -> str:
        return str(payload.get("generated_at", "")).strip()
