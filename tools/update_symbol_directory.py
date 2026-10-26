"""Refresh a public name/code directory from KIS master files (no credentials).

Only numeric six-character KOSPI/KOSDAQ stocks and ETFs fit the current board
contract. This directory is an input aid, not a trading eligibility check.
"""

# ruff: noqa: INP001
from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

BASE = "https://new.real.download.dws.co.kr/common/master/"
CODE_LENGTH = 6
PREFIX_LENGTH = 63
MIN_MARKET_ROWS = 500
DESTINATION = Path(__file__).resolve().parents[1] / "web/data/symbols.json"


class MasterError(ValueError):
    """Reject incomplete upstream data without replacing the published directory."""


def parse_master(payload: bytes, market: str) -> list[list[str]]:
    """Read fixed CP949 byte fields and retain supported stock identities."""
    rows = []
    seen = set()
    for raw in payload.splitlines():
        if len(raw) < PREFIX_LENGTH:
            raise MasterError("TRUNCATED_MASTER_ROW")
        # Fixed byte fields: short code 9, ISIN 12, CP949 name 40, group 2.
        code = raw[:9].decode("ascii").strip()
        if len(code) != CODE_LENGTH or not code.isascii() or not code.isdigit():
            continue
        name = raw[21:61].decode("cp949").strip()
        group = raw[61:63].decode("ascii")
        if group not in {"ST", "EF"}:
            continue
        if not name or code in seen:
            raise MasterError("INVALID_OR_DUPLICATE_MASTER_IDENTITY")
        seen.add(code)
        rows.append([code, name, market, "ETF" if group == "EF" else "주식"])
    return rows


def main() -> None:
    """Download both approved HTTPS sources and atomically refresh the asset."""
    rows, sources = [], []
    for market in ["KOSPI", "KOSDAQ"]:
        filename = market.lower() + "_code.mst"
        url = BASE + filename + ".zip"
        with urlopen(url, timeout=30) as response:  # noqa: S310 -- URL uses fixed HTTPS base.
            archive = response.read(5 * 1024 * 1024 + 1)
        if len(archive) > 5 * 1024 * 1024:
            raise MasterError("ARCHIVE_TOO_LARGE")
        with ZipFile(io.BytesIO(archive)) as zipped:
            info = zipped.getinfo(filename)
            if info.file_size > 20 * 1024 * 1024:
                raise MasterError("EXPANDED_MASTER_TOO_LARGE")
            data = zipped.read(info)
        records = parse_master(data, market)
        if len(records) < MIN_MARKET_ROWS:
            raise MasterError("INCOMPLETE_MASTER")
        rows.extend(records)
        sources.append(
            {
                "url": url,
                "sha256": hashlib.sha256(archive).hexdigest(),
                "rows": len(records),
            }
        )
    if len({row[0] for row in rows}) != len(rows):
        raise MasterError("CROSS_MARKET_DUPLICATE_CODE")
    result = {
        "schemaVersion": 1,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "한국투자증권 공개 종목 마스터",
        "sources": sources,
        "scope": "숫자 6자리 KOSPI/KOSDAQ 주식·ETF (KONEX·영문 혼합 코드 제외)",
        "symbols": sorted(rows),
    }
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary = DESTINATION.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(DESTINATION)
    print(f"Updated {len(rows)} symbols")  # noqa: T201 -- CLI result.


if __name__ == "__main__":
    main()
