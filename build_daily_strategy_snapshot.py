# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from data.csv_loader import BarData, CsvDataLoader
from quant_bottom_reversal_backtest import detect_daily_bottom_pattern


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = BASE_DIR / "data" / "daily"
DEFAULT_OUTPUT = BASE_DIR / "condition_snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="일봉 CSV로 전략별 다음날 매매 후보를 생성합니다.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_DIR), help="일봉 CSV 폴더")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="저장할 후보 snapshot 경로")
    parser.add_argument("--min-bars", type=int, default=80, help="전략 판정에 필요한 최소 일봉 수")
    parser.add_argument("--max-per-strategy", type=int, default=12, help="전략별 최대 후보 수")
    return parser.parse_args()


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct(current: float, base: float) -> float:
    return (current - base) / base * 100.0 if base > 0 else 0.0


def code_name_from_file(path: Path) -> tuple[str, str]:
    stem = path.stem
    if "_" in stem:
        code, name = stem.split("_", 1)
        return code.strip(), name.strip()
    return stem.strip(), ""


def load_daily_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.glob("*.csv") if path.is_file())


def bottom_reversal_candidate(bars: list[BarData]) -> tuple[bool, float, str]:
    args = argparse.Namespace(
        lookback=60,
        ma_short=5,
        ma_mid=20,
        min_decline_pct=25.0,
        near_low_pct=16.0,
        recovery_pct=5.0,
        volume_ratio=1.2,
    )
    ok, pattern = detect_daily_bottom_pattern(bars, len(bars) - 1, args)
    if not ok:
        return False, 0.0, pattern
    recent = bars[-60:]
    recent_high = max(bar.high for bar in recent)
    recent_low = min(bar.low for bar in recent)
    score = pct(recent_high, recent_low) + pct(bars[-1].close, recent_low)
    return True, score, pattern


def pullback_leader_candidate(bars: list[BarData]) -> tuple[bool, float, str]:
    if len(bars) < 80:
        return False, 0.0, "not_enough_history"

    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    close = closes[-1]
    ma5 = avg(closes[-5:])
    ma20 = avg(closes[-20:])
    ma60 = avg(closes[-60:])
    prev_ma20 = avg(closes[-25:-5])
    recent_high = max(bar.high for bar in bars[-40:])
    pullback_pct = pct(recent_high, close)
    volume_ratio = volumes[-1] / avg(volumes[-21:-1]) if avg(volumes[-21:-1]) > 0 else 1.0

    if not (ma20 > ma60 and ma20 >= prev_ma20):
        return False, 0.0, "trend_not_up"
    if not (5.0 <= pullback_pct <= 15.0):
        return False, 0.0, "pullback_range_miss"
    if close < ma20 * 0.97:
        return False, 0.0, "ma20_broken"
    if close < ma5 and bars[-1].close <= bars[-1].open:
        return False, 0.0, "rebound_not_confirmed"
    if volume_ratio < 0.8:
        return False, 0.0, "volume_too_low"

    score = (ma20 / ma60 - 1.0) * 100.0 + (15.0 - pullback_pct) + volume_ratio
    return True, score, "daily_pullback_leader"


def close_buy_candidate(bars: list[BarData]) -> tuple[bool, float, str]:
    if len(bars) < 60:
        return False, 0.0, "not_enough_history"

    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    today = bars[-1]
    close = today.close
    ma5 = avg(closes[-5:])
    ma20 = avg(closes[-20:])
    prev_high_20 = max(bar.high for bar in bars[-21:-1])
    volume_ratio = volumes[-1] / avg(volumes[-21:-1]) if avg(volumes[-21:-1]) > 0 else 1.0
    day_return = pct(close, today.open)
    change_from_prev = pct(close, closes[-2])

    recovered_ma5 = closes[-2] < ma5 <= close
    breakout = close >= prev_high_20 * 0.995
    healthy_candle = close > today.open and day_return <= 8.0 and change_from_prev <= 10.0

    if not healthy_candle:
        return False, 0.0, "candle_not_healthy"
    if not (recovered_ma5 or breakout):
        return False, 0.0, "no_close_signal"
    if volume_ratio < 1.0:
        return False, 0.0, "volume_not_enough"
    if close < ma20 * 0.92:
        return False, 0.0, "too_far_below_ma20"

    score = volume_ratio * 10.0 + max(0.0, change_from_prev) + (5.0 if breakout else 0.0)
    return True, score, "daily_close_buy"


def build_rows(files: list[Path], min_bars: int, max_per_strategy: int) -> list[dict]:
    by_symbol: dict[str, dict] = {}
    scored_by_strategy: dict[str, list[tuple[float, str]]] = defaultdict(list)

    for path in files:
        code, name = code_name_from_file(path)
        bars = CsvDataLoader(path, code=code).load_bars()
        if len(bars) < min_bars:
            continue

        checks = [
            ("bottom_reversal", bottom_reversal_candidate(bars)),
            ("leader_pullback", pullback_leader_candidate(bars)),
            ("close_buy", close_buy_candidate(bars)),
        ]
        for strategy_name, (ok, score, reason) in checks:
            if not ok:
                continue
            row = by_symbol.setdefault(
                code,
                {
                    "symbol": code,
                    "name": name,
                    "strategies": [],
                    "daily_reasons": [],
                    "last_date": bars[-1].dt.strftime("%Y-%m-%d"),
                    "last_close": bars[-1].close,
                },
            )
            row["strategies"].append(strategy_name)
            row["daily_reasons"].append(f"{strategy_name}:{reason}:{score:.2f}")
            scored_by_strategy[strategy_name].append((score, code))

    allowed_by_strategy = {}
    for strategy_name, values in scored_by_strategy.items():
        values.sort(reverse=True)
        allowed_by_strategy[strategy_name] = {code for _, code in values[:max_per_strategy]}

    rows = []
    for row in by_symbol.values():
        strategies = [
            strategy_name
            for strategy_name in sorted(set(row["strategies"]))
            if row["symbol"] in allowed_by_strategy.get(strategy_name, set())
        ]
        if not strategies:
            continue
        row["strategies"] = strategies
        rows.append(row)

    rows.sort(key=lambda item: (",".join(item["strategies"]), item["symbol"]))
    return rows


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input)
    if not input_dir.is_absolute():
        input_dir = BASE_DIR / input_dir
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path

    files = load_daily_files(input_dir)
    rows = build_rows(files, min_bars=args.min_bars, max_per_strategy=args.max_per_strategy)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "condition_name": "일봉_전략후보",
        "source": "daily_strategy_snapshot",
        "count": len(rows),
        "codes": rows,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = defaultdict(int)
    for row in rows:
        for strategy_name in row.get("strategies", []):
            counts[strategy_name] += 1
    print(f"일봉 후보 저장 완료 | path={output_path} count={len(rows)} counts={dict(counts)}")
    for row in rows[:20]:
        print(f"{row['symbol']} {row.get('name', '')} strategies={','.join(row.get('strategies', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
