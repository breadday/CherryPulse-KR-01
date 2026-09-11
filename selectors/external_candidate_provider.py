from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional


KOREA_MARKET_TIMEZONE = timezone(timedelta(hours=9), "Asia/Seoul")


class ExternalCandidateError(ValueError):
    pass


@dataclass(frozen=True)
class ExternalCandidate:
    symbol: str
    name: str
    selection_date: date
    strategy_tag: str
    intended_holding_period: str
    source: str
    expires_at: datetime


class ExternalCandidateProvider:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self, as_of: Optional[datetime] = None) -> List[ExternalCandidate]:
        effective_as_of = as_of or datetime.now(KOREA_MARKET_TIMEZONE)
        if effective_as_of.tzinfo is None or effective_as_of.utcoffset() is None:
            raise ExternalCandidateError("as_of must include timezone information")

        payload = self._read_payload()
        if not isinstance(payload, dict):
            raise ExternalCandidateError("candidate document must be a JSON object")

        schema_version = payload.get("schema_version")
        if type(schema_version) is not int or schema_version != self.SCHEMA_VERSION:
            raise ExternalCandidateError(
                f"schema_version must be {self.SCHEMA_VERSION}"
            )

        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list):
            raise ExternalCandidateError("candidates must be an array")

        candidates: List[ExternalCandidate] = []
        identities = set()
        for index, raw_candidate in enumerate(raw_candidates):
            candidate = self._parse_candidate(raw_candidate, index)
            identity = (candidate.symbol, candidate.strategy_tag)
            if identity in identities:
                raise ExternalCandidateError(
                    "duplicate candidate identity "
                    f"symbol={candidate.symbol} strategy_tag={candidate.strategy_tag}"
                )
            identities.add(identity)

            market_date = effective_as_of.astimezone(KOREA_MARKET_TIMEZONE).date()
            if candidate.selection_date > market_date:
                raise ExternalCandidateError(
                    f"candidate[{index}].selection_date cannot be in the future"
                )
            if candidate.expires_at <= effective_as_of:
                continue
            candidates.append(candidate)

        return candidates

    def _read_payload(self):
        try:
            raw = self.path.read_text(encoding="utf-8-sig")
        except FileNotFoundError as exc:
            raise ExternalCandidateError(
                f"candidate file not found: {self.path}"
            ) from exc
        except OSError as exc:
            raise ExternalCandidateError(
                f"candidate file could not be read: {self.path}"
            ) from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExternalCandidateError(
                f"candidate file contains invalid JSON: {self.path}"
            ) from exc

    def _parse_candidate(self, raw_candidate, index: int) -> ExternalCandidate:
        if not isinstance(raw_candidate, dict):
            raise ExternalCandidateError(f"candidate[{index}] must be an object")

        symbol = self._required_text(raw_candidate, "symbol", index)
        if re.fullmatch(r"[0-9]{6}", symbol) is None:
            raise ExternalCandidateError(
                f"candidate[{index}].symbol must be a 6-digit code"
            )

        selection_date_text = self._required_text(
            raw_candidate, "selection_date", index
        )
        try:
            parsed_selection_date = date.fromisoformat(selection_date_text)
        except ValueError as exc:
            raise ExternalCandidateError(
                f"candidate[{index}].selection_date must be an ISO date"
            ) from exc
        if parsed_selection_date.isoformat() != selection_date_text:
            raise ExternalCandidateError(
                f"candidate[{index}].selection_date must be an ISO date"
            )

        expires_at_text = self._required_text(raw_candidate, "expires_at", index)
        normalized_expires_at = (
            f"{expires_at_text[:-1]}+00:00"
            if expires_at_text.endswith("Z")
            else expires_at_text
        )
        try:
            parsed_expires_at = datetime.fromisoformat(normalized_expires_at)
        except ValueError as exc:
            raise ExternalCandidateError(
                f"candidate[{index}].expires_at must be an ISO datetime"
            ) from exc
        if parsed_expires_at.tzinfo is None or parsed_expires_at.utcoffset() is None:
            raise ExternalCandidateError(
                f"candidate[{index}].expires_at must include timezone information"
            )

        return ExternalCandidate(
            symbol=symbol,
            name=self._required_text(raw_candidate, "name", index),
            selection_date=parsed_selection_date,
            strategy_tag=self._required_text(raw_candidate, "strategy_tag", index),
            intended_holding_period=self._required_text(
                raw_candidate, "intended_holding_period", index
            ),
            source=self._required_text(raw_candidate, "source", index),
            expires_at=parsed_expires_at,
        )

    @staticmethod
    def _required_text(raw_candidate: dict, field: str, index: int) -> str:
        value = raw_candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ExternalCandidateError(
                f"candidate[{index}].{field} must be a non-empty string"
            )
        return value.strip()
