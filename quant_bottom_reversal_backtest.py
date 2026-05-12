from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from data.csv_loader import BarData, CsvDataLoader


BASE_DIR = Path(__file__).resolve().parent


@dataclass
class QuantTrade:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    hold_days: int
    pnl_pct: float
    exit_reason: str
    pattern: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="일봉 바닥패턴 전략을 CSV 데이터로 백테스트합니다. CSV에는 date/open/high/low/close/volume 컬럼이 필요합니다."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="CSV 파일 또는 CSV 폴더 경로입니다. 폴더면 종목별 *.csv 전체를 검증합니다.",
    )
    parser.add_argument("--code", default="", help="CSV에 종목코드 컬럼이 없을 때 사용할 기본 종목코드")
    parser.add_argument("--output", default="results/quant_bottom_reversal_report.csv", help="거래 결과 CSV 저장 경로")
    parser.add_argument("--lookback", type=int, default=60, help="최근 고점/저점 확인 기간")
    parser.add_argument("--min-decline-pct", type=float, default=25.0, help="최근 고점 대비 최소 조정률(%)")
    parser.add_argument("--near-low-pct", type=float, default=16.0, help="최근 저점 대비 현재 종가가 너무 멀지 않은 기준(%)")
    parser.add_argument("--recovery-pct", type=float, default=5.0, help="최근 저점 대비 최소 반등률(%)")
    parser.add_argument("--ma-short", type=int, default=5, help="단기 이동평균")
    parser.add_argument("--ma-mid", type=int, default=20, help="중기 이동평균")
    parser.add_argument("--volume-ratio", type=float, default=1.2, help="전일 거래량 / 20일 평균 거래량 최소 비율")
    parser.add_argument("--max-hold-days", type=int, default=20, help="최대 보유 일수")
    parser.add_argument("--stop-loss-pct", type=float, default=-5.0, help="손절률(%)")
    parser.add_argument("--take-profit-pct", type=float, default=20.0, help="목표수익률(%)")
    parser.add_argument("--ma-exit", action="store_true", help="수익권에서 종가가 5일선 아래로 내려오면 청산")
    parser.add_argument("--fee-pct", type=float, default=0.04, help="왕복 수수료/세금 가정치(%)")
    return parser.parse_args()


def resolve_input_files(input_path: str) -> list[Path]:
    path = Path(input_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    if path.is_dir():
        files_by_code: dict[str, Path] = {}
        for file_path in sorted(path.glob("*.csv")):
            code = file_path.stem.split("_", 1)[0]
            if not code.isdigit():
                code = file_path.stem

            # 같은 종목 CSV가 여러 번 저장된 경우 최신 파일 하나만 검증에 사용한다.
            previous = files_by_code.get(code)
            if previous is None or file_path.stat().st_mtime >= previous.stat().st_mtime:
                files_by_code[code] = file_path
        return sorted(files_by_code.values())
    return [path]


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct(current: float, base: float) -> float:
    return (current - base) / base * 100.0 if base > 0 else 0.0


def detect_daily_bottom_pattern(bars: list[BarData], idx: int, args: argparse.Namespace) -> tuple[bool, str]:
    if idx < max(args.lookback, args.ma_mid) + 1:
        return False, "not_enough_history"

    window = bars[idx - args.lookback:idx]
    closes = [bar.close for bar in bars[:idx]]
    recent_high = max(bar.high for bar in window)
    recent_low = min(bar.low for bar in window)
    close = bars[idx].close

    decline_pct = pct(recent_high, recent_low)
    near_low_pct = pct(close, recent_low)
    recovery_pct = near_low_pct
    ma_short = avg([bar.close for bar in bars[idx - args.ma_short + 1:idx + 1]])
    prev_ma_short = avg([bar.close for bar in bars[idx - args.ma_short:idx]])
    volume_avg = avg([bar.volume for bar in bars[idx - 20:idx]])
    volume_ratio = bars[idx].volume / volume_avg if volume_avg > 0 else 1.0

    if decline_pct < args.min_decline_pct:
        return False, "decline_not_enough"
    if near_low_pct > args.near_low_pct:
        return False, "too_far_from_low"
    if recovery_pct < args.recovery_pct and close < ma_short:
        return False, "recovery_not_enough"
    if volume_ratio < args.volume_ratio:
        return False, "volume_not_enough"

    lows = [bar.low for bar in window]
    first_zone_end = max(1, int(len(window) * 0.65))
    first_low_idx = min(range(first_zone_end), key=lambda x: lows[x])
    second_start = first_low_idx + 5
    w_bottom = False
    if second_start < len(window) - 1:
        second_low_idx = min(range(second_start, len(window)), key=lambda x: lows[x])
        first_low = lows[first_low_idx]
        second_low = lows[second_low_idx]
        low_gap_pct = abs(second_low - first_low) / first_low * 100.0 if first_low > 0 else 999.0
        middle_high = max(bar.high for bar in window[first_low_idx + 1:second_low_idx] or window)
        w_bottom = low_gap_pct <= 5.0 and (close >= ma_short or close >= middle_high * 0.98)

    v_reversal = (
        recovery_pct >= max(args.recovery_pct, 5.0)
        and len(closes) >= 3
        and bars[idx].close >= bars[idx - 1].close >= bars[idx - 2].close
    )

    rounded_bottom = close >= ma_short and ma_short >= prev_ma_short and recovery_pct >= args.recovery_pct

    if w_bottom:
        return True, "daily_w_bottom"
    if v_reversal:
        return True, "daily_v_reversal"
    if rounded_bottom:
        return True, "daily_rounded_bottom"
    return False, "pattern_not_confirmed"


def simulate_trade(bars: list[BarData], entry_idx: int, pattern: str, args: argparse.Namespace) -> QuantTrade | None:
    if entry_idx + 1 >= len(bars):
        return None

    entry_bar = bars[entry_idx + 1]
    entry_price = entry_bar.open
    if entry_price <= 0:
        return None

    exit_idx = min(len(bars) - 1, entry_idx + args.max_hold_days)
    exit_price = bars[exit_idx].close
    exit_reason = "max_hold"

    for idx in range(entry_idx + 1, exit_idx + 1):
        bar = bars[idx]
        low_pnl = pct(bar.low, entry_price)
        high_pnl = pct(bar.high, entry_price)
        close_pnl = pct(bar.close, entry_price)

        if low_pnl <= args.stop_loss_pct:
            exit_idx = idx
            exit_price = entry_price * (1.0 + args.stop_loss_pct / 100.0)
            exit_reason = "stop_loss"
            break
        if high_pnl >= args.take_profit_pct:
            exit_idx = idx
            exit_price = entry_price * (1.0 + args.take_profit_pct / 100.0)
            exit_reason = "take_profit"
            break
        if args.ma_exit and idx >= args.ma_short:
            ma_short = avg([x.close for x in bars[idx - args.ma_short + 1:idx + 1]])
            if close_pnl > 0 and bar.close < ma_short:
                exit_idx = idx
                exit_price = bar.close
                exit_reason = "ma_exit"
                break

    net_pnl_pct = pct(exit_price, entry_price) - args.fee_pct
    return QuantTrade(
        symbol=entry_bar.code,
        entry_date=entry_bar.dt.strftime("%Y-%m-%d"),
        exit_date=bars[exit_idx].dt.strftime("%Y-%m-%d"),
        entry_price=round(entry_price, 2),
        exit_price=round(exit_price, 2),
        hold_days=max(1, exit_idx - entry_idx),
        pnl_pct=round(net_pnl_pct, 4),
        exit_reason=exit_reason,
        pattern=pattern,
    )


def backtest_bars(bars: list[BarData], args: argparse.Namespace) -> list[QuantTrade]:
    trades: list[QuantTrade] = []
    next_allowed_idx = 0
    for idx in range(len(bars)):
        if idx < next_allowed_idx:
            continue
        ok, pattern = detect_daily_bottom_pattern(bars, idx, args)
        if not ok:
            continue
        trade = simulate_trade(bars, idx, pattern, args)
        if trade is None:
            continue
        trades.append(trade)
        next_allowed_idx = idx + trade.hold_days
    return trades


def summarize(trades: list[QuantTrade]) -> str:
    if not trades:
        return "거래 없음: 조건이 너무 엄격하거나 데이터가 부족합니다."
    pnl_values = [trade.pnl_pct for trade in trades]
    wins = [x for x in pnl_values if x > 0]
    losses = [x for x in pnl_values if x <= 0]
    win_rate = len(wins) / len(trades) * 100.0
    avg_win = mean(wins) if wins else 0.0
    avg_loss = mean(losses) if losses else 0.0
    expectancy = mean(pnl_values)
    total = sum(pnl_values)
    return (
        f"거래수={len(trades)} 승률={win_rate:.2f}% "
        f"평균수익={avg_win:.2f}% 평균손실={avg_loss:.2f}% "
        f"기대값={expectancy:.2f}% 누적={total:.2f}%"
    )


def write_report(path: str, trades: list[QuantTrade]) -> Path:
    output_path = Path(path)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "entry_date",
                "exit_date",
                "entry_price",
                "exit_price",
                "hold_days",
                "pnl_pct",
                "exit_reason",
                "pattern",
            ],
        )
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade.__dict__)
    return output_path


def main() -> int:
    args = parse_args()
    files = resolve_input_files(args.input)
    all_trades: list[QuantTrade] = []

    for file_path in files:
        code = args.code or file_path.stem.split("_", 1)[0]
        loader = CsvDataLoader(file_path, code=code)
        bars = loader.load_bars()
        trades = backtest_bars(bars, args)
        all_trades.extend(trades)
        print(f"{file_path.name}: {summarize(trades)}")

    report_path = write_report(args.output, all_trades)
    print(f"전체: {summarize(all_trades)}")
    print(f"리포트 저장: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
