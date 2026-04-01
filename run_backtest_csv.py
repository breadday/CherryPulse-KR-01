# run_backtest_csv.py

from __future__ import annotations

from pathlib import Path

from backtest.csv_feed import bars_to_ticks
from backtest.runner import BacktestRunner
from config import STRATEGY_CONFIG
from data.csv_loader import CsvDataLoader


def main():
    csv_path = Path("data/sample/005930_1m.csv")

    loader = CsvDataLoader(filepath=csv_path, code="005930")

    info = loader.inspect()
    print("CSV 검사 결과")
    print(f"- 파일: {info['filepath']}")
    print(f"- 구분자: {info['delimiter']}")
    print(f"- 헤더: {info['header']}")
    print(f"- 미리보기: {info['preview_rows']}")
    print(f"- 유효 라인 수: {info['line_count']}")

    bars = loader.load_bars()
    ticks = bars_to_ticks(bars)

    print("\nCSV 로드 완료")
    print(f"- bar 개수: {len(bars)}")
    print(f"- 시작 시각: {bars[0].dt}")
    print(f"- 종료 시각: {bars[-1].dt}")
    print(f"- 첫 종가: {bars[0].close}")
    print(f"- 마지막 종가: {bars[-1].close}")

    runner = BacktestRunner(strategy_config=STRATEGY_CONFIG, initial_cash=5_000_000)
    result = runner.run(ticks)

    print("\n백테스트 결과")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()