from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from statistics import mean
from types import SimpleNamespace

from data.csv_loader import CsvDataLoader
from quant_bottom_reversal_backtest import backtest_bars, resolve_input_files


BASE_DIR = Path(__file__).resolve().parent


@dataclass
class OptimizationRow:
    rank: int
    trades: int
    win_rate: float
    expectancy: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    min_decline_pct: float
    near_low_pct: float
    recovery_pct: float
    volume_ratio: float
    stop_loss_pct: float
    take_profit_pct: float
    max_hold_days: int
    ma_exit: bool
    pattern_summary: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="일봉 바닥패턴 매매 조건 조합을 최적화합니다.")
    parser.add_argument("--input", default="data/daily", help="일봉 CSV 파일 또는 폴더")
    parser.add_argument("--output", default="results/quant_bottom_reversal_optimization.csv", help="최적화 결과 CSV")
    parser.add_argument("--min-trades", type=int, default=5, help="후보에 포함할 최소 거래 수")
    parser.add_argument("--top", type=int, default=20, help="화면에 출력할 상위 조합 수")
    return parser.parse_args()


def summarize_pattern(trades) -> str:
    buckets: dict[str, list[float]] = {}
    for trade in trades:
        buckets.setdefault(trade.pattern, []).append(float(trade.pnl_pct))

    parts = []
    for pattern, values in sorted(buckets.items()):
        wins = [v for v in values if v > 0]
        win_rate = len(wins) / len(values) * 100.0 if values else 0.0
        parts.append(f"{pattern}:{len(values)}건/{win_rate:.0f}%/{sum(values):.1f}%")
    return " | ".join(parts)


def score_trades(trades, params: dict, rank: int = 0) -> OptimizationRow:
    pnl_values = [float(trade.pnl_pct) for trade in trades]
    wins = [v for v in pnl_values if v > 0]
    losses = [v for v in pnl_values if v <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return OptimizationRow(
        rank=rank,
        trades=len(trades),
        win_rate=(len(wins) / len(trades) * 100.0) if trades else 0.0,
        expectancy=mean(pnl_values) if pnl_values else 0.0,
        total_pnl=sum(pnl_values),
        avg_win=mean(wins) if wins else 0.0,
        avg_loss=mean(losses) if losses else 0.0,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        min_decline_pct=params["min_decline_pct"],
        near_low_pct=params["near_low_pct"],
        recovery_pct=params["recovery_pct"],
        volume_ratio=params["volume_ratio"],
        stop_loss_pct=params["stop_loss_pct"],
        take_profit_pct=params["take_profit_pct"],
        max_hold_days=params["max_hold_days"],
        ma_exit=params["ma_exit"],
        pattern_summary=summarize_pattern(trades),
    )


def build_param_grid() -> list[dict]:
    grid = []
    for values in product(
        [15.0, 20.0, 25.0],
        [8.0, 12.0, 16.0],
        [2.0, 3.0, 5.0],
        [1.0, 1.2, 1.5],
        [-5.0, -7.0, -10.0],
        [10.0, 15.0, 20.0],
        [10, 20, 30],
        [True, False],
    ):
        (
            min_decline_pct,
            near_low_pct,
            recovery_pct,
            volume_ratio,
            stop_loss_pct,
            take_profit_pct,
            max_hold_days,
            ma_exit,
        ) = values
        grid.append(
            {
                "lookback": 60,
                "ma_short": 5,
                "ma_mid": 20,
                "fee_pct": 0.04,
                "min_decline_pct": min_decline_pct,
                "near_low_pct": near_low_pct,
                "recovery_pct": recovery_pct,
                "volume_ratio": volume_ratio,
                "stop_loss_pct": stop_loss_pct,
                "take_profit_pct": take_profit_pct,
                "max_hold_days": max_hold_days,
                "ma_exit": ma_exit,
            }
        )
    return grid


def write_rows(path: str, rows: list[OptimizationRow]) -> Path:
    output_path = Path(path)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(OptimizationRow.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)
    return output_path


def main() -> int:
    args = parse_args()
    files = resolve_input_files(args.input)
    bars_by_file = []
    for file_path in files:
        loader = CsvDataLoader(file_path, code=file_path.stem.split("_")[0])
        bars_by_file.append(loader.load_bars())

    rows: list[OptimizationRow] = []
    for params in build_param_grid():
        ns = SimpleNamespace(**params)
        trades = []
        for bars in bars_by_file:
            trades.extend(backtest_bars(bars, ns))
        if len(trades) < args.min_trades:
            continue
        rows.append(score_trades(trades, params))

    rows.sort(key=lambda row: (row.expectancy, row.profit_factor, row.trades), reverse=True)
    for idx, row in enumerate(rows, start=1):
        row.rank = idx

    output_path = write_rows(args.output, rows)
    print(f"최적화 완료 | 조합={len(rows)} report={output_path}")
    for row in rows[: args.top]:
        print(
            f"#{row.rank} trades={row.trades} win={row.win_rate:.1f}% "
            f"exp={row.expectancy:.2f}% total={row.total_pnl:.2f}% "
            f"pf={row.profit_factor:.2f} "
            f"decline={row.min_decline_pct} near_low={row.near_low_pct} "
            f"recovery={row.recovery_pct} vr={row.volume_ratio} "
            f"stop={row.stop_loss_pct} take={row.take_profit_pct} "
            f"hold={row.max_hold_days} ma_exit={row.ma_exit} | {row.pattern_summary}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
