# -*- coding: utf-8 -*-
"""
run_replay_cases_final.py

오프장 재생 테스트 실행기
- case1~case5 테스트 데이터 생성
- TradingEngine에 직접 틱 주입
- DRY_RUN 체결 자동 처리
- 결과 CSV / TXT 저장

실행:
    python run_replay_cases_final.py
    python run_replay_cases_final.py --repeat 5
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import config
from engine import TradingEngine
from strategy.momentum_intraday import MomentumIntradayStrategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="오프장 재생 테스트")
    parser.add_argument("--repeat", type=int, default=3, help="각 case 반복 횟수")
    parser.add_argument(
        "--cases",
        type=str,
        default="case1,case2,case3,case4,case5",
        help="쉼표 구분 case 목록",
    )
    parser.add_argument("--output-dir", type=str, default="replay_test_output", help="결과 저장 폴더")
    parser.add_argument("--sleep-ms", type=int, default=0, help="틱 사이 지연(ms)")
    return parser.parse_args()


def patch_config() -> None:
    defaults = {
        "DRY_RUN": True,
        "LIVE_MODE": False,
        "ENABLE_TELEGRAM_LOG": False,
        "STOP_LOSS_PCT": -0.02,
        "PARTIAL_TAKE_PROFIT_PCT": 0.02,
        "PARTIAL_TAKE_RATIO": 0.5,
        "TAKE_PROFIT_PCT": 0.03,
        "BREAKEVEN_ENABLED": True,
        "TRAILING_STOP_ENABLED": True,
        "TRAILING_STOP_PCT": 0.01,
    }
    for k, v in defaults.items():
        if not hasattr(config, k):
            setattr(config, k, v)


def build_logger(name: str, path: Path) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


class FakeNewsProvider:
    def __init__(self, logger=None):
        self.logger = logger

    def get_scores(self, symbol: str):
        return {
            "news_score": 0.0,
            "theme_score": 0.0,
            "leader_score": 0.0,
            "total_external_score": 0.0,
        }


class FakeBroker:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._real_tick_callback = None
        self._fill_callback = None
        self._msg_callback = None

    def set_real_tick_callback(self, callback):
        self._real_tick_callback = callback

    def set_fill_callback(self, callback):
        self._fill_callback = callback

    def set_msg_callback(self, callback):
        self._msg_callback = callback

    def connect(self):
        self.logger.info("FakeBroker connect")

    def shutdown(self):
        self.logger.info("FakeBroker shutdown")

    def get_deposit(self, password: str = ""):
        return 10_000_000

    def get_positions(self, password: str = ""):
        return []

    def get_pending_orders(self, password: str = ""):
        return []

    def place_order(self, signal):
        from core.models import OrderStatus
        now_ts = datetime.now()
        order = SimpleNamespace(
            order_id=f"SIM-{uuid.uuid4().hex[:10]}",
            broker_order_id=f"BROKER-{uuid.uuid4().hex[:10]}",
            symbol=getattr(signal, "symbol", ""),
            side=getattr(signal, "side", ""),
            qty=int(getattr(signal, "qty", 0)),
            price=float(getattr(signal, "price", 0) or 0),
            order_type=getattr(signal, "order_type", ""),
            status=OrderStatus.SUBMITTED,
            filled_qty=0,
            avg_fill_price=0.0,
            reason=getattr(signal, "reason", ""),
            ts=now_ts,
            created_at=now_ts,
            updated_at=now_ts,
        )
        self.logger.info(
            f"FakeBroker 주문 | id={order.order_id} symbol={order.symbol} side={order.side} qty={order.qty}"
        )
        return order


@dataclass
class RunRow:
    case_name: str
    run_no: int
    ticks: int
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_profit_pct: float
    avg_loss_pct: float
    net_pnl: float
    final_qty: int


def tick(
    symbol: str,
    price: int,
    trade_volume: int,
    price_change_pct: float,
    trade_strength: float,
    volume_ratio: float,
    news_score: float = 0.0,
    theme_score: float = 0.0,
    leader_score: float = 0.0,
) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "price": price,
        "trade_volume": trade_volume,
        "price_change_pct": price_change_pct,
        "trade_strength": trade_strength,
        "volume_ratio": volume_ratio,
        "news_score": news_score,
        "theme_score": theme_score,
        "leader_score": leader_score,
    }


def generate_case_ticks(case_name: str, symbol: str) -> List[Dict[str, Any]]:
    if case_name == "case1":
        prices = [70000, 70300, 70650, 71000, 71500, 72000, 72400]
        strengths = [150, 178, 182, 175, 168, 160, 155]
        ratios = [1.70, 1.85, 1.95, 1.88, 1.82, 1.75, 1.70]
        chgs = [1.0, 1.8, 2.1, 2.5, 3.2, 3.8, 4.3]
    elif case_name == "case2":
        prices = [70000, 70400, 70300, 69900, 69400, 68900, 68600]
        strengths = [152, 180, 150, 126, 110, 95, 90]
        ratios = [1.72, 1.92, 1.65, 1.35, 1.12, 1.00, 0.96]
        chgs = [1.0, 1.9, 1.4, 0.4, -0.4, -1.1, -1.6]
    elif case_name == "case3":
        prices = [70000, 70500, 70600, 70200, 69900, 69700, 69600]
        strengths = [155, 182, 178, 120, 100, 92, 88]
        ratios = [1.75, 1.95, 1.90, 1.30, 1.12, 1.02, 0.98]
        chgs = [1.1, 2.0, 2.1, 1.0, 0.1, -0.2, -0.4]
    elif case_name == "case4":
        prices = [70000, 70400, 70800, 71500, 72000, 72600, 73100, 72300, 71900]
        strengths = [148, 176, 180, 172, 168, 166, 160, 128, 120]
        ratios = [1.68, 1.88, 1.92, 1.85, 1.82, 1.78, 1.72, 1.42, 1.35]
        chgs = [1.0, 1.9, 2.3, 3.1, 3.6, 4.1, 4.5, 3.0, 2.3]
    elif case_name == "case5":
        prices = [70000, 70100, 70080, 70120, 70090, 70110, 70070]
        strengths = [110, 115, 112, 114, 109, 108, 105]
        ratios = [1.10, 1.18, 1.12, 1.16, 1.08, 1.05, 1.00]
        chgs = [0.3, 0.4, 0.25, 0.35, 0.2, 0.2, 0.05]
    else:
        raise ValueError(f"unknown case: {case_name}")

    rows = []
    for i, p in enumerate(prices):
        rows.append(
            tick(
                symbol=symbol,
                price=p,
                trade_volume=1000 + (i * 100),
                price_change_pct=chgs[i],
                trade_strength=strengths[i],
                volume_ratio=ratios[i],
                news_score=0.2,
                theme_score=0.1 if case_name in ("case1", "case4") else 0.0,
                leader_score=0.1 if case_name in ("case1", "case3", "case4") else 0.0,
            )
        )
    return rows


def save_csv(path: Path, rows: List[RunRow]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def build_summary_text(rows: List[RunRow]) -> str:
    total_runs = len(rows)
    total_trades = sum(r.total_trades for r in rows)
    total_wins = sum(r.wins for r in rows)
    total_losses = sum(r.losses for r in rows)
    total_net_pnl = round(sum(r.net_pnl for r in rows), 2)

    lines = []
    lines.append("오프장 재생 테스트 요약")
    lines.append("=" * 50)
    lines.append(f"실행 수: {total_runs}")
    lines.append(f"총 거래수: {total_trades}")
    lines.append(f"총 승: {total_wins}")
    lines.append(f"총 패: {total_losses}")
    lines.append(f"총 순손익: {total_net_pnl}")
    lines.append("")

    by_case: Dict[str, List[RunRow]] = {}
    for row in rows:
        by_case.setdefault(row.case_name, []).append(row)

    for case_name in sorted(by_case.keys()):
        chunk = by_case[case_name]
        avg_win = round(sum(x.win_rate for x in chunk) / len(chunk), 4)
        avg_pnl = round(sum(x.net_pnl for x in chunk) / len(chunk), 2)
        avg_trades = round(sum(x.total_trades for x in chunk) / len(chunk), 4)
        lines.append(f"[{case_name}] runs={len(chunk)} avg_win_rate={avg_win} avg_net_pnl={avg_pnl} avg_trades={avg_trades}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    patch_config()

    base_dir = Path(__file__).resolve().parent
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = base_dir / args.output_dir / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    logger = build_logger("replay_test", out_dir / "run.log")
    logger.info("재생 테스트 시작")

    cases = [x.strip() for x in args.cases.split(",") if x.strip()]
    results: List[RunRow] = []

    for case_name in cases:
        for run_no in range(1, args.repeat + 1):
            symbol = f"T{case_name[-1]}{run_no:02d}"
            logger.info(f"[RUN] {case_name} #{run_no} symbol={symbol}")

            broker = FakeBroker(logger)
            strategy = MomentumIntradayStrategy(config={})
            engine = TradingEngine(
                broker=broker,
                strategy=strategy,
                logger=logger,
                telegram=None,
                initial_cash=5_000_000,
                test_name=f"{case_name}_r{run_no}",
            )

            # 외부 뉴스 의존 제거
            engine.news_provider = FakeNewsProvider(logger=logger)

            engine.start()

            rows = generate_case_ticks(case_name, symbol)
            for raw_tick in rows:
                engine.on_real_tick(raw_tick)
                if args.sleep_ms > 0:
                    time.sleep(args.sleep_ms / 1000.0)

            engine.stop()

            summary = engine.get_trade_summary()
            final_qty = getattr(engine.portfolio.get_position(symbol), "qty", 0)

            result = RunRow(
                case_name=case_name,
                run_no=run_no,
                ticks=len(rows),
                total_trades=int(summary.get("total_trades", 0)),
                wins=int(summary.get("wins", 0)),
                losses=int(summary.get("losses", 0)),
                win_rate=float(summary.get("win_rate", 0.0)),
                avg_profit_pct=float(summary.get("avg_profit_pct", 0.0)),
                avg_loss_pct=float(summary.get("avg_loss_pct", 0.0)),
                net_pnl=float(summary.get("net_pnl", 0.0)),
                final_qty=int(final_qty),
            )
            results.append(result)

            logger.info(
                f"[DONE] {case_name} #{run_no} "
                f"trades={result.total_trades} wins={result.wins} losses={result.losses} "
                f"net_pnl={result.net_pnl} final_qty={result.final_qty}"
            )

    csv_path = out_dir / "results.csv"
    txt_path = out_dir / "summary.txt"

    save_csv(csv_path, results)
    txt_path.write_text(build_summary_text(results), encoding="utf-8")

    print("=" * 60)
    print("재생 테스트 완료")
    print(f"CSV: {csv_path}")
    print(f"TXT: {txt_path}")
    print(f"LOG: {out_dir / 'run.log'}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
