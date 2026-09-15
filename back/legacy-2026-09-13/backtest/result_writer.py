# backtest/result_writer.py

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


def ensure_result_dir(result_dir: str | Path = "results") -> Path:
    path = Path(result_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_summary_csv(results: list[dict], filepath: str | Path) -> None:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "symbol",
        "file",
        "bars",
        "trades",
        "wins",
        "losses",
        "win_rate",
        "total_return",
        "mdd",
        "sharpe",
        "final_cash",
    ]

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            writer.writerow({
                "symbol": r.get("symbol"),
                "file": r.get("file"),
                "bars": r.get("bars"),
                "trades": r.get("trades"),
                "wins": r.get("wins"),
                "losses": r.get("losses"),
                "win_rate": r.get("win_rate"),
                "total_return": r.get("total_return"),
                "mdd": r.get("mdd"),
                "sharpe": r.get("sharpe"),
                "final_cash": r.get("final_cash"),
            })


def iter_trade_rows(results: list[dict]) -> Iterable[dict]:
    for r in results:
        symbol = r.get("symbol")
        file = r.get("file")
        for trade in r.get("trade_log", []):
            yield {
                "symbol": symbol,
                "file": file,
                "entry_price": trade.get("entry_price"),
                "exit_price": trade.get("exit_price"),
                "qty": trade.get("qty"),
                "pnl": trade.get("pnl"),
                "reason": trade.get("reason"),
                "entry_ts": trade.get("entry_ts"),
                "exit_ts": trade.get("exit_ts"),
            }


def write_trades_csv(results: list[dict], filepath: str | Path) -> None:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "symbol",
        "file",
        "entry_price",
        "exit_price",
        "qty",
        "pnl",
        "reason",
        "entry_ts",
        "exit_ts",
    ]

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in iter_trade_rows(results):
            writer.writerow(row)