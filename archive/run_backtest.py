# run_backtest.py  : 실행 예제 파일 

from datetime import datetime, timedelta

from backtest.runner import BacktestRunner, BacktestTick
from config import STRATEGY_CONFIG


def build_sample_ticks():
    ticks = []

    base_time = datetime(2026, 3, 31, 9, 0, 0)
    prices = [10000, 10050, 10100, 10200, 10350, 10400, 10320, 10250, 10180, 10100]

    for i, price in enumerate(prices):
        ticks.append(
            BacktestTick(
                symbol="005930",
                price=price,
                volume=1000 + i * 100,
                ts=base_time + timedelta(seconds=i * 30),
                price_change_pct=1.0,
                trade_strength=150,
                volume_ratio=2.0,
            )
        )

    return ticks


if __name__ == "__main__":
    runner = BacktestRunner(strategy_config=STRATEGY_CONFIG, initial_cash=5_000_000)
    ticks = build_sample_ticks()
    result = runner.run(ticks)

    print("백테스트 결과")
    for k, v in result.items():
        print(f"{k}: {v}")