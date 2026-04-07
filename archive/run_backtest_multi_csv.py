# run_backtest_multi_csv.py

from __future__ import annotations

from pathlib import Path
from statistics import mean

from backtest.csv_feed import bars_to_ticks
from backtest.result_writer import ensure_result_dir, write_summary_csv, write_trades_csv
from backtest.runner import BacktestRunner
from config import STRATEGY_CONFIG
from data.csv_loader import CsvDataLoader


def run_single_csv(csv_path: Path, initial_cash: float = 5_000_000) -> dict:
    symbol = csv_path.stem.split("_")[0]

    loader = CsvDataLoader(filepath=csv_path, code=symbol)
    bars = loader.load_bars()
    ticks = bars_to_ticks(bars)

    runner = BacktestRunner(
        strategy_config=STRATEGY_CONFIG,
        initial_cash=initial_cash,
    )
    result = runner.run(ticks)

    return {
        "symbol": symbol,
        "file": str(csv_path),
        "bars": len(bars),
        "trades": result.get("trades", 0),
        "wins": result.get("wins", 0),
        "losses": result.get("losses", 0),
        "win_rate": result.get("win_rate", 0.0),
        "total_return": result.get("total_return", 0.0),
        "mdd": result.get("mdd", 0.0),
        "sharpe": result.get("sharpe", 0.0),
        "final_cash": result.get("final_cash", initial_cash),
        "trade_log": runner.trades,
    }


def print_result_table(results: list[dict]) -> None:
    print("\n종목별 결과")
    print("-" * 120)
    print(
        f"{'symbol':<10}"
        f"{'bars':>8}"
        f"{'trades':>8}"
        f"{'wins':>8}"
        f"{'losses':>8}"
        f"{'win_rate':>12}"
        f"{'return':>12}"
        f"{'mdd':>12}"
        f"{'sharpe':>12}"
        f"{'final_cash':>15}"
    )
    print("-" * 120)

    for r in results:
        print(
            f"{r['symbol']:<10}"
            f"{r['bars']:>8}"
            f"{r['trades']:>8}"
            f"{r['wins']:>8}"
            f"{r['losses']:>8}"
            f"{r['win_rate']:>12.4f}"
            f"{r['total_return']:>12.4f}"
            f"{r['mdd']:>12.4f}"
            f"{r['sharpe']:>12.4f}"
            f"{r['final_cash']:>15.2f}"
        )

    print("-" * 120)


def print_summary(results: list[dict]) -> None:
    if not results:
        print("\n전체 요약: 결과 없음")
        return

    total_symbols = len(results)
    total_trades = sum(r["trades"] for r in results)
    total_wins = sum(r["wins"] for r in results)
    total_losses = sum(r["losses"] for r in results)

    avg_win_rate = mean(r["win_rate"] for r in results)
    avg_return = mean(r["total_return"] for r in results)
    avg_mdd = mean(r["mdd"] for r in results)
    avg_sharpe = mean(r["sharpe"] for r in results)
    avg_final_cash = mean(r["final_cash"] for r in results)

    best_return = max(results, key=lambda x: x["total_return"])
    worst_return = min(results, key=lambda x: x["total_return"])

    print("\n전체 요약")
    print(f"- 테스트 종목 수: {total_symbols}")
    print(f"- 총 거래 수: {total_trades}")
    print(f"- 총 승리 수: {total_wins}")
    print(f"- 총 패배 수: {total_losses}")
    print(f"- 평균 승률: {avg_win_rate:.4f}")
    print(f"- 평균 수익률: {avg_return:.4f}")
    print(f"- 평균 MDD: {avg_mdd:.4f}")
    print(f"- 평균 Sharpe: {avg_sharpe:.4f}")
    print(f"- 평균 최종자산: {avg_final_cash:.2f}")
    print(
        f"- 최고 수익 종목: {best_return['symbol']} "
        f"(return={best_return['total_return']:.4f}, final_cash={best_return['final_cash']:.2f})"
    )
    print(
        f"- 최저 수익 종목: {worst_return['symbol']} "
        f"(return={worst_return['total_return']:.4f}, final_cash={worst_return['final_cash']:.2f})"
    )


def print_trade_logs(results: list[dict]) -> None:
    print("\n체결 로그")
    print("-" * 120)

    has_trade = False
    for r in results:
        if not r["trade_log"]:
            continue

        has_trade = True
        print(f"\n[{r['symbol']}]")
        for i, trade in enumerate(r["trade_log"], start=1):
            print(
                f"{i}. "
                f"entry={trade['entry_price']} "
                f"exit={trade['exit_price']} "
                f"qty={trade['qty']} "
                f"pnl={trade['pnl']} "
                f"reason={trade['reason']} "
                f"entry_ts={trade['entry_ts']} "
                f"exit_ts={trade['exit_ts']}"
            )

    if not has_trade:
        print("체결 로그 없음")


def main():
    data_dir = Path("data/sample")
    csv_files = sorted(data_dir.glob("*.csv"))

    if not csv_files:
        print(f"CSV 파일이 없습니다: {data_dir}")
        return

    print("다중 CSV 백테스트 시작")
    print(f"- 대상 폴더: {data_dir}")
    print(f"- 파일 수: {len(csv_files)}")

    results: list[dict] = []

    for csv_path in csv_files:
        try:
            print(f"\n[실행] {csv_path}")
            result = run_single_csv(csv_path)
            results.append(result)
            print(
                f"완료 | symbol={result['symbol']} "
                f"trades={result['trades']} "
                f"win_rate={result['win_rate']:.4f} "
                f"final_cash={result['final_cash']:.2f}"
            )
        except Exception as e:
            print(f"실패 | file={csv_path} | error={e}")

    if not results:
        print("\n성공한 백테스트 결과가 없습니다.")
        return

    results.sort(key=lambda x: x["total_return"], reverse=True)

    print_result_table(results)
    print_summary(results)
    print_trade_logs(results)

    result_dir = ensure_result_dir("results")
    summary_path = result_dir / "backtest_summary.csv"
    trades_path = result_dir / "backtest_trades.csv"

    write_summary_csv(results, summary_path)
    write_trades_csv(results, trades_path)

    print("\n결과 파일 저장 완료")
    print(f"- 요약: {summary_path}")
    print(f"- 체결로그: {trades_path}")


if __name__ == "__main__":
    main()