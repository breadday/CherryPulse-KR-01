# -*- coding: utf-8 -*-
"""
analyze_replay_results.py

STEP 2
- replay_test_output 결과 CSV 분석 업그레이드
- 전체 / case별 승률, 순손익, 기대값 계산
- 문제 case 자동 표시
- CSV / JSON / TXT 리포트 생성

지원 입력
1) run_replay_cases_final.py 가 만든 results.csv
2) 직접 지정한 CSV 파일

실행 예시
    python analyze_replay_results.py
    python analyze_replay_results.py --input replay_test_output/20260405_165818/results.csv
    python analyze_replay_results.py --latest
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------
@dataclass
class Row:
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


@dataclass
class CaseSummary:
    case_name: str
    runs: int
    total_trades: int
    wins: int
    losses: int
    no_trade_runs: int
    open_position_runs: int
    run_win_rate_pct: float
    trade_win_rate_pct: float
    avg_net_pnl: float
    total_net_pnl: float
    avg_profit_pct: float
    avg_loss_pct: float
    expectancy_pct: float
    profit_factor: float
    risk_flag: str
    note: str


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="replay_test_output 결과 분석")
    parser.add_argument("--input", type=str, default="", help="직접 지정할 results.csv 경로")
    parser.add_argument("--base-dir", type=str, default="replay_test_output", help="기본 결과 폴더")
    parser.add_argument("--latest", action="store_true", help="가장 최근 results.csv 분석")
    parser.add_argument("--output-dir", type=str, default="analysis_output", help="분석 결과 저장 폴더")
    return parser.parse_args()


# ---------------------------------------------------------
# 파일 탐색
# ---------------------------------------------------------
def find_latest_results_csv(base_dir: Path) -> Optional[Path]:
    if not base_dir.exists():
        return None

    candidates = sorted(base_dir.glob("*/results.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    return None


def resolve_input_path(args: argparse.Namespace) -> Path:
    if args.input:
        path = Path(args.input).resolve()
        if not path.exists():
            raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
        return path

    base_dir = Path(args.base_dir).resolve()
    latest = find_latest_results_csv(base_dir)
    if latest is None:
        raise FileNotFoundError(f"results.csv를 찾지 못했습니다: {base_dir}")

    return latest


# ---------------------------------------------------------
# 로드
# ---------------------------------------------------------
def safe_int(v, default=0) -> int:
    try:
        if v in ("", None):
            return default
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return default


def safe_float(v, default=0.0) -> float:
    try:
        if v in ("", None):
            return default
        return float(str(v).replace(",", "").strip())
    except Exception:
        return default


def load_rows(path: Path) -> List[Row]:
    rows: List[Row] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(
                Row(
                    case_name=str(r.get("case_name", "")).strip(),
                    run_no=safe_int(r.get("run_no", 0)),
                    ticks=safe_int(r.get("ticks", 0)),
                    total_trades=safe_int(r.get("total_trades", 0)),
                    wins=safe_int(r.get("wins", 0)),
                    losses=safe_int(r.get("losses", 0)),
                    win_rate=safe_float(r.get("win_rate", 0.0)),
                    avg_profit_pct=safe_float(r.get("avg_profit_pct", 0.0)),
                    avg_loss_pct=safe_float(r.get("avg_loss_pct", 0.0)),
                    net_pnl=safe_float(r.get("net_pnl", 0.0)),
                    final_qty=safe_int(r.get("final_qty", 0)),
                )
            )
    return rows


# ---------------------------------------------------------
# 분석
# ---------------------------------------------------------
def calc_profit_factor(avg_profit_pct: float, avg_loss_pct: float, wins: int, losses: int) -> float:
    gross_profit = avg_profit_pct * wins
    gross_loss = abs(avg_loss_pct) * losses
    if gross_loss <= 0:
        return 0.0 if gross_profit <= 0 else 999.0
    return round(gross_profit / gross_loss, 4)


def calc_expectancy_pct(trade_win_rate_pct: float, avg_profit_pct: float, avg_loss_pct: float) -> float:
    p = trade_win_rate_pct / 100.0
    q = 1.0 - p
    return round((p * avg_profit_pct) + (q * avg_loss_pct), 4)


def analyze_case(case_name: str, chunk: List[Row]) -> CaseSummary:
    runs = len(chunk)
    total_trades = sum(x.total_trades for x in chunk)
    wins = sum(x.wins for x in chunk)
    losses = sum(x.losses for x in chunk)
    no_trade_runs = sum(1 for x in chunk if x.total_trades == 0)
    open_position_runs = sum(1 for x in chunk if x.final_qty > 0)

    run_win_rate_pct = round((sum(1 for x in chunk if x.net_pnl > 0) / runs) * 100.0, 4) if runs else 0.0
    trade_win_rate_pct = round((wins / total_trades) * 100.0, 4) if total_trades else 0.0

    total_net_pnl = round(sum(x.net_pnl for x in chunk), 2)
    avg_net_pnl = round(total_net_pnl / runs, 2) if runs else 0.0

    win_profit_values = [x.avg_profit_pct for x in chunk if x.wins > 0 and x.avg_profit_pct > 0]
    loss_values = [x.avg_loss_pct for x in chunk if x.losses > 0 and x.avg_loss_pct < 0]

    avg_profit_pct = round(sum(win_profit_values) / len(win_profit_values), 4) if win_profit_values else 0.0
    avg_loss_pct = round(sum(loss_values) / len(loss_values), 4) if loss_values else 0.0

    expectancy_pct = calc_expectancy_pct(trade_win_rate_pct, avg_profit_pct, avg_loss_pct)
    profit_factor = calc_profit_factor(avg_profit_pct, avg_loss_pct, wins, losses)

    flags: List[str] = []
    notes: List[str] = []

    if total_trades == 0:
        flags.append("CHECK")
        notes.append("거래 없음")
    if open_position_runs > 0:
        flags.append("CHECK")
        notes.append("종료 후 잔여 포지션 존재")
    if total_net_pnl < 0:
        flags.append("BAD")
        notes.append("총 순손익 음수")
    if trade_win_rate_pct < 40 and total_trades > 0:
        flags.append("BAD")
        notes.append("승률 낮음")
    if expectancy_pct < 0 and total_trades > 0:
        flags.append("BAD")
        notes.append("기대값 음수")
    if profit_factor != 999.0 and 0 < profit_factor < 1.0:
        flags.append("BAD")
        notes.append("Profit Factor 1 미만")
    if not flags:
        flags.append("OK")
        notes.append("정상")

    risk_flag = "BAD" if "BAD" in flags else "CHECK" if "CHECK" in flags else "OK"

    return CaseSummary(
        case_name=case_name,
        runs=runs,
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        no_trade_runs=no_trade_runs,
        open_position_runs=open_position_runs,
        run_win_rate_pct=run_win_rate_pct,
        trade_win_rate_pct=trade_win_rate_pct,
        avg_net_pnl=avg_net_pnl,
        total_net_pnl=total_net_pnl,
        avg_profit_pct=avg_profit_pct,
        avg_loss_pct=avg_loss_pct,
        expectancy_pct=expectancy_pct,
        profit_factor=profit_factor,
        risk_flag=risk_flag,
        note=" / ".join(notes),
    )


def analyze_rows(rows: List[Row]) -> Dict[str, object]:
    by_case: Dict[str, List[Row]] = defaultdict(list)
    for row in rows:
        by_case[row.case_name].append(row)

    case_summaries = [analyze_case(case_name, chunk) for case_name, chunk in sorted(by_case.items())]

    total_runs = len(rows)
    total_trades = sum(x.total_trades for x in rows)
    total_wins = sum(x.wins for x in rows)
    total_losses = sum(x.losses for x in rows)
    total_net_pnl = round(sum(x.net_pnl for x in rows), 2)

    overall_trade_win_rate_pct = round((total_wins / total_trades) * 100.0, 4) if total_trades else 0.0

    all_win_profit_values = [x.avg_profit_pct for x in rows if x.wins > 0 and x.avg_profit_pct > 0]
    all_loss_values = [x.avg_loss_pct for x in rows if x.losses > 0 and x.avg_loss_pct < 0]

    overall_avg_profit_pct = round(sum(all_win_profit_values) / len(all_win_profit_values), 4) if all_win_profit_values else 0.0
    overall_avg_loss_pct = round(sum(all_loss_values) / len(all_loss_values), 4) if all_loss_values else 0.0
    overall_expectancy_pct = calc_expectancy_pct(overall_trade_win_rate_pct, overall_avg_profit_pct, overall_avg_loss_pct)
    overall_profit_factor = calc_profit_factor(overall_avg_profit_pct, overall_avg_loss_pct, total_wins, total_losses)

    best_case = None
    worst_case = None
    if case_summaries:
        best_case = max(case_summaries, key=lambda x: (x.total_net_pnl, x.trade_win_rate_pct, x.expectancy_pct)).case_name
        worst_case = min(case_summaries, key=lambda x: (x.total_net_pnl, x.trade_win_rate_pct, x.expectancy_pct)).case_name

    return {
        "overall": {
            "total_runs": total_runs,
            "total_trades": total_trades,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "overall_trade_win_rate_pct": overall_trade_win_rate_pct,
            "overall_avg_profit_pct": overall_avg_profit_pct,
            "overall_avg_loss_pct": overall_avg_loss_pct,
            "overall_expectancy_pct": overall_expectancy_pct,
            "overall_profit_factor": overall_profit_factor,
            "total_net_pnl": total_net_pnl,
            "best_case": best_case,
            "worst_case": worst_case,
        },
        "cases": case_summaries,
    }


# ---------------------------------------------------------
# 저장
# ---------------------------------------------------------
def save_case_summary_csv(path: Path, summaries: List[CaseSummary]) -> None:
    if not summaries:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(summaries[0]).keys()))
        writer.writeheader()
        for row in summaries:
            writer.writerow(asdict(row))


def build_report_text(source_csv: Path, analysis: Dict[str, object]) -> str:
    overall = analysis["overall"]
    cases: List[CaseSummary] = analysis["cases"]

    lines: List[str] = []
    lines.append("STEP 2 분석 리포트")
    lines.append("=" * 60)
    lines.append(f"source_csv: {source_csv}")
    lines.append(f"generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("[전체 요약]")
    lines.append(f"- total_runs: {overall['total_runs']}")
    lines.append(f"- total_trades: {overall['total_trades']}")
    lines.append(f"- total_wins: {overall['total_wins']}")
    lines.append(f"- total_losses: {overall['total_losses']}")
    lines.append(f"- overall_trade_win_rate_pct: {overall['overall_trade_win_rate_pct']}")
    lines.append(f"- overall_avg_profit_pct: {overall['overall_avg_profit_pct']}")
    lines.append(f"- overall_avg_loss_pct: {overall['overall_avg_loss_pct']}")
    lines.append(f"- overall_expectancy_pct: {overall['overall_expectancy_pct']}")
    lines.append(f"- overall_profit_factor: {overall['overall_profit_factor']}")
    lines.append(f"- total_net_pnl: {overall['total_net_pnl']}")
    lines.append(f"- best_case: {overall['best_case']}")
    lines.append(f"- worst_case: {overall['worst_case']}")
    lines.append("")
    lines.append("[case별 요약]")

    for row in cases:
        lines.append(f"{row.case_name}")
        lines.append(f"  - risk_flag: {row.risk_flag}")
        lines.append(f"  - runs: {row.runs}")
        lines.append(f"  - total_trades: {row.total_trades}")
        lines.append(f"  - wins/losses: {row.wins}/{row.losses}")
        lines.append(f"  - run_win_rate_pct: {row.run_win_rate_pct}")
        lines.append(f"  - trade_win_rate_pct: {row.trade_win_rate_pct}")
        lines.append(f"  - avg_net_pnl: {row.avg_net_pnl}")
        lines.append(f"  - total_net_pnl: {row.total_net_pnl}")
        lines.append(f"  - avg_profit_pct: {row.avg_profit_pct}")
        lines.append(f"  - avg_loss_pct: {row.avg_loss_pct}")
        lines.append(f"  - expectancy_pct: {row.expectancy_pct}")
        lines.append(f"  - profit_factor: {row.profit_factor}")
        lines.append(f"  - note: {row.note}")
        lines.append("")

    bad_cases = [x.case_name for x in cases if x.risk_flag == "BAD"]
    check_cases = [x.case_name for x in cases if x.risk_flag == "CHECK"]

    lines.append("[자동 판정]")
    lines.append(f"- BAD: {', '.join(bad_cases) if bad_cases else '(없음)'}")
    lines.append(f"- CHECK: {', '.join(check_cases) if check_cases else '(없음)'}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    input_csv = resolve_input_path(args)
    rows = load_rows(input_csv)
    if not rows:
        raise ValueError(f"분석할 데이터가 없습니다: {input_csv}")

    analysis = analyze_rows(rows)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir).resolve() / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    case_csv_path = out_dir / "case_summary.csv"
    json_path = out_dir / "analysis.json"
    txt_path = out_dir / "analysis_report.txt"

    save_case_summary_csv(case_csv_path, analysis["cases"])
    json_path.write_text(
        json.dumps(
            {
                "source_csv": str(input_csv),
                "overall": analysis["overall"],
                "cases": [asdict(x) for x in analysis["cases"]],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    txt_path.write_text(build_report_text(input_csv, analysis), encoding="utf-8")

    overall = analysis["overall"]
    print("=" * 60)
    print("STEP 2 분석 완료")
    print(f"source: {input_csv}")
    print(f"total_trades: {overall['total_trades']}")
    print(f"win_rate: {overall['overall_trade_win_rate_pct']}")
    print(f"expectancy: {overall['overall_expectancy_pct']}")
    print(f"net_pnl: {overall['total_net_pnl']}")
    print(f"best_case: {overall['best_case']}")
    print(f"worst_case: {overall['worst_case']}")
    print(f"CSV : {case_csv_path}")
    print(f"JSON: {json_path}")
    print(f"TXT : {txt_path}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
