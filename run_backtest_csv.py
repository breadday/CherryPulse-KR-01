# run_backtest_csv.py  :  CSV 백테스트 실행 파일

from __future__ import annotations

from pathlib import Path

from data.csv_loader import CsvDataLoader
from backtest.csv_feed import bars_to_ticks
from backtest.runner import BacktestRunner
from strategy.momentum_intraday import MomentumIntradayStrategy


def main():
    csv_path = Path("data/sample/005930_1m.csv")

    loader = CsvDataLoader(filepath=csv_path, code="005930")
    bars = loader.load_bars()
    ticks = bars_to_ticks(bars)

    print(f"CSV 로드 완료: {csv_path}")
    print(f"바 개수: {len(bars)}")
    if bars:
        print(f"시작: {bars[0].dt}, 종료: {bars[-1].dt}")

    strategy = MomentumIntradayStrategy()
    runner = BacktestRunner(strategy=strategy, initial_cash=5_000_000)

    result = runner.run(ticks)

    print("\n백테스트 결과")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()