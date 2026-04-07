# -*- coding: utf-8 -*-
"""
run_bulk_cases.py

STEP 1
- case1 ~ case5 반복 실행
- 결과 자동 누적
- 로그 저장 ON/OFF 옵션 지원
- 실시간 로그 저장 옵션 지원
- 거래 요약 자동 파싱
- 누적 CSV / JSON / TXT 리포트 생성

실행 예시
    python run_bulk_cases.py
    python run_bulk_cases.py --repeat 5
    python run_bulk_cases.py --cases case1,case3,case5
    python run_bulk_cases.py --log-mode realtime
    python run_bulk_cases.py --log-mode end
    python run_bulk_cases.py --log-mode off
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


FLOAT_RE = r"[-+]?\d+(?:\.\d+)?"


@dataclass
class RunRow:
    batch_id: str
    case_name: str
    run_no: int
    started_at: str
    finished_at: str
    elapsed_sec: float
    return_code: int
    status: str
    test_name: str
    stdout_file: str
    stderr_file: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    win_rate_pct: float = 0.0
    avg_return_pct: float = 0.0
    avg_loss_pct: float = 0.0
    expectancy_pct: float = 0.0
    net_pnl: float = 0.0
    profit_factor: float = 0.0
    avg_holding_min: float = 0.0
    parse_ok: bool = False
    parse_note: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CherryPulse case1~case5 대량 테스트 자동 실행기")
    parser.add_argument("--repeat", type=int, default=3, help="각 case 반복 횟수")
    parser.add_argument(
        "--cases",
        type=str,
        default="case1,case2,case3,case4,case5",
        help="쉼표 구분 케이스 목록"
    )
    parser.add_argument(
        "--target",
        type=str,
        default="main_live_param.py",
        help="실행 대상 파일명"
    )
    parser.add_argument(
        "--python",
        type=str,
        default=sys.executable,
        help="파이썬 실행 파일 경로"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="각 실행 사이 대기 초"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="bulk_test_output",
        help="결과 저장 폴더"
    )
    parser.add_argument(
        "--log-mode",
        type=str,
        choices=["realtime", "end", "off"],
        default="realtime",
        help=(
            "로그 저장 방식: "
            "realtime=실행 중 실시간 저장, "
            "end=실행 종료 후 저장, "
            "off=로그 파일 미생성"
        ),
    )
    parser.add_argument(
        "--print-live",
        action="store_true",
        help="실시간 로그를 콘솔에도 같이 출력"
    )
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_int(v: Optional[str], default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return default


def safe_float(v: Optional[str], default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", "").strip())
    except Exception:
        return default


def parse_trade_summary(text: str) -> Dict[str, object]:
    result = {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "win_rate_pct": 0.0,
        "avg_return_pct": 0.0,
        "avg_loss_pct": 0.0,
        "expectancy_pct": 0.0,
        "net_pnl": 0.0,
        "profit_factor": 0.0,
        "avg_holding_min": 0.0,
        "parse_ok": False,
        "parse_note": "",
    }

    if not text or not text.strip():
        result["parse_note"] = "empty_output"
        return result

    patterns = {
        "total_trades": re.compile(r"총 거래수:\s*(\d+)"),
        "wins_losses_draws": re.compile(r"승/패/보합:\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)"),
        "win_rate_pct": re.compile(r"승률:\s*(" + FLOAT_RE + r")%"),
        "avg_return_pct": re.compile(r"평균 수익률:\s*(" + FLOAT_RE + r")%"),
        "avg_loss_pct": re.compile(r"평균 손실률:\s*(" + FLOAT_RE + r")%"),
        "expectancy_pct": re.compile(r"기대값:\s*(" + FLOAT_RE + r")%"),
        "net_pnl": re.compile(r"순손익:\s*(" + FLOAT_RE + r")원"),
        "profit_factor": re.compile(r"Profit Factor:\s*(" + FLOAT_RE + r")"),
        "avg_holding_min": re.compile(r"평균 보유시간:\s*(" + FLOAT_RE + r")분"),
    }

    total_trades_match = patterns["total_trades"].search(text)
    wld_match = patterns["wins_losses_draws"].search(text)

    if total_trades_match:
        result["total_trades"] = safe_int(total_trades_match.group(1))

    if wld_match:
        result["wins"] = safe_int(wld_match.group(1))
        result["losses"] = safe_int(wld_match.group(2))
        result["draws"] = safe_int(wld_match.group(3))

    for key in ["win_rate_pct", "avg_return_pct", "avg_loss_pct", "expectancy_pct", "net_pnl", "profit_factor", "avg_holding_min"]:
        m = patterns[key].search(text)
        if m:
            result[key] = safe_float(m.group(1))

    if result["total_trades"] > 0 or (result["wins"] + result["losses"] + result["draws"]) > 0:
        result["parse_ok"] = True
        result["parse_note"] = "summary_block"
        return result

    perf_matches = re.findall(
        r"\[PERFORMANCE\].*?trades=(\d+).*?wins=(\d+).*?losses=(\d+).*?win_rate=(" + FLOAT_RE + r")%.*?avg_profit=(" + FLOAT_RE + r")%.*?avg_loss=(" + FLOAT_RE + r")%.*?net_pnl=(" + FLOAT_RE + r")",
        text,
        flags=re.DOTALL,
    )

    if perf_matches:
        trades, wins, losses, win_rate, avg_profit, avg_loss, net_pnl = perf_matches[-1]
        result["total_trades"] = safe_int(trades)
        result["wins"] = safe_int(wins)
        result["losses"] = safe_int(losses)
        result["draws"] = max(result["total_trades"] - result["wins"] - result["losses"], 0)
        result["win_rate_pct"] = safe_float(win_rate)
        result["avg_return_pct"] = safe_float(avg_profit)
        result["avg_loss_pct"] = safe_float(avg_loss)
        result["net_pnl"] = safe_float(net_pnl)
        result["parse_ok"] = True
        result["parse_note"] = "performance_log"
        return result

    result["parse_note"] = "summary_not_found"
    return result


def save_csv(path: Path, rows: List[RunRow]) -> None:
    if not rows:
        return

    fieldnames = list(asdict(rows[0]).keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def save_json(path: Path, rows: List[RunRow], summary: Dict[str, object]) -> None:
    payload = {
        "summary": summary,
        "rows": [asdict(row) for row in rows],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_summary(rows: List[RunRow]) -> Dict[str, object]:
    case_summary: Dict[str, Dict[str, float]] = {}

    for row in rows:
        box = case_summary.setdefault(
            row.case_name,
            {
                "runs": 0,
                "success_runs": 0,
                "failed_runs": 0,
                "parsed_runs": 0,
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "net_pnl_sum": 0.0,
                "win_rate_sum": 0.0,
                "avg_return_sum": 0.0,
                "avg_loss_sum": 0.0,
                "profit_factor_sum": 0.0,
            },
        )

        box["runs"] += 1
        if row.return_code == 0:
            box["success_runs"] += 1
        else:
            box["failed_runs"] += 1

        if row.parse_ok:
            box["parsed_runs"] += 1
            box["total_trades"] += row.total_trades
            box["wins"] += row.wins
            box["losses"] += row.losses
            box["draws"] += row.draws
            box["net_pnl_sum"] += row.net_pnl
            box["win_rate_sum"] += row.win_rate_pct
            box["avg_return_sum"] += row.avg_return_pct
            box["avg_loss_sum"] += row.avg_loss_pct
            box["profit_factor_sum"] += row.profit_factor

    for case_name, box in case_summary.items():
        parsed_runs = int(box["parsed_runs"])
        box["avg_win_rate_pct"] = round(box["win_rate_sum"] / parsed_runs, 4) if parsed_runs else 0.0
        box["avg_return_pct"] = round(box["avg_return_sum"] / parsed_runs, 4) if parsed_runs else 0.0
        box["avg_loss_pct"] = round(box["avg_loss_sum"] / parsed_runs, 4) if parsed_runs else 0.0
        box["avg_profit_factor"] = round(box["profit_factor_sum"] / parsed_runs, 4) if parsed_runs else 0.0
        box["net_pnl_sum"] = round(box["net_pnl_sum"], 2)

    grand = {
        "total_runs": len(rows),
        "success_runs": sum(1 for x in rows if x.return_code == 0),
        "failed_runs": sum(1 for x in rows if x.return_code != 0),
        "parsed_runs": sum(1 for x in rows if x.parse_ok),
        "cases": case_summary,
    }
    return grand


def build_report_text(summary: Dict[str, object], rows: List[RunRow]) -> str:
    lines: List[str] = []
    lines.append("대량 테스트 통합 요약")
    lines.append("=" * 60)
    lines.append(f"전체 실행 수: {summary['total_runs']}")
    lines.append(f"성공 실행 수: {summary['success_runs']}")
    lines.append(f"실패 실행 수: {summary['failed_runs']}")
    lines.append(f"파싱 성공 수: {summary['parsed_runs']}")
    lines.append("")

    cases: Dict[str, Dict[str, object]] = summary["cases"]  # type: ignore[assignment]
    for case_name in sorted(cases.keys()):
        item = cases[case_name]
        lines.append(f"[{case_name}]")
        lines.append(f"- runs: {item['runs']}")
        lines.append(f"- success_runs: {item['success_runs']}")
        lines.append(f"- failed_runs: {item['failed_runs']}")
        lines.append(f"- parsed_runs: {item['parsed_runs']}")
        lines.append(f"- total_trades: {item['total_trades']}")
        lines.append(f"- wins/losses/draws: {item['wins']}/{item['losses']}/{item['draws']}")
        lines.append(f"- avg_win_rate_pct: {item['avg_win_rate_pct']}")
        lines.append(f"- avg_return_pct: {item['avg_return_pct']}")
        lines.append(f"- avg_loss_pct: {item['avg_loss_pct']}")
        lines.append(f"- avg_profit_factor: {item['avg_profit_factor']}")
        lines.append(f"- net_pnl_sum: {item['net_pnl_sum']}")
        lines.append("")

    failed = [x for x in rows if x.return_code != 0]
    if failed:
        lines.append("실패 실행")
        lines.append("-" * 60)
        for row in failed:
            lines.append(
                f"{row.case_name} #{row.run_no} | rc={row.return_code} | stdout={row.stdout_file} | stderr={row.stderr_file}"
            )
        lines.append("")

    return "\n".join(lines)


def build_command(args: argparse.Namespace, target_path: Path, case_name: str, test_name: str) -> List[str]:
    return [
        args.python,
        str(target_path),
        "--mode", "dry",
        "--case", case_name,
        "--test-name", test_name,
    ]


def run_capture_end(command: List[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def run_realtime(command: List[str], stdout_path: Optional[Path], stderr_path: Optional[Path], print_live: bool) -> tuple[int, str, str]:
    stdout_chunks: List[str] = []
    stderr_chunks: List[str] = []

    out_fp = open(stdout_path, "w", encoding="utf-8") if stdout_path else None
    err_fp = open(stderr_path, "w", encoding="utf-8") if stderr_path else None

    try:
        proc = subprocess.Popen(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )

        assert proc.stdout is not None

        for line in proc.stdout:
            stdout_chunks.append(line)
            if out_fp:
                out_fp.write(line)
                out_fp.flush()
            if print_live:
                print(line, end="")

        return_code = proc.wait()
        stdout_text = "".join(stdout_chunks)
        stderr_text = "".join(stderr_chunks)
        return return_code, stdout_text, stderr_text

    finally:
        if out_fp:
            out_fp.close()
        if err_fp:
            err_fp.close()


def execute_case(
    command: List[str],
    log_mode: str,
    stdout_path: Path,
    stderr_path: Path,
    print_live: bool,
) -> tuple[int, str, str]:
    if log_mode == "realtime":
        return run_realtime(command, stdout_path, stderr_path, print_live)

    if log_mode == "end":
        return_code, stdout_text, stderr_text = run_capture_end(command)
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
        return return_code, stdout_text, stderr_text

    return run_capture_end(command)


def main() -> int:
    args = parse_args()

    cases = [x.strip() for x in args.cases.split(",") if x.strip()]
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path(__file__).resolve().parent
    output_dir = (base_dir / args.output_dir / batch_id).resolve()
    logs_dir = output_dir / "logs"

    ensure_dir(output_dir)
    if args.log_mode in ("realtime", "end"):
        ensure_dir(logs_dir)

    target_path = (base_dir / args.target).resolve()
    if not target_path.exists():
        print(f"[오류] 대상 파일이 없습니다: {target_path}")
        return 1

    rows: List[RunRow] = []

    print("=" * 70)
    print("대량 테스트 시작")
    print(f"- batch_id: {batch_id}")
    print(f"- target: {target_path.name}")
    print(f"- cases: {', '.join(cases)}")
    print(f"- repeat: {args.repeat}")
    print(f"- log_mode: {args.log_mode}")
    print(f"- output: {output_dir}")
    print("=" * 70)

    for case_name in cases:
        for run_no in range(1, args.repeat + 1):
            test_name = f"{batch_id}_{case_name}_r{run_no}"
            started_at = now_text()
            start_ts = time.time()

            command = build_command(args, target_path, case_name, test_name)

            if args.log_mode in ("realtime", "end"):
                stdout_path = logs_dir / f"{case_name}_run{run_no}_stdout.txt"
                stderr_path = logs_dir / f"{case_name}_run{run_no}_stderr.txt"
                stdout_file = str(stdout_path)
                stderr_file = str(stderr_path)
            else:
                stdout_path = Path("")
                stderr_path = Path("")
                stdout_file = ""
                stderr_file = ""

            print(f"[RUN] {case_name} #{run_no} 시작")

            return_code, stdout_text, stderr_text = execute_case(
                command=command,
                log_mode=args.log_mode,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                print_live=args.print_live,
            )

            finished_at = now_text()
            elapsed_sec = round(time.time() - start_ts, 3)

            parsed = parse_trade_summary((stdout_text or "") + "\n" + (stderr_text or ""))

            row = RunRow(
                batch_id=batch_id,
                case_name=case_name,
                run_no=run_no,
                started_at=started_at,
                finished_at=finished_at,
                elapsed_sec=elapsed_sec,
                return_code=return_code,
                status="OK" if return_code == 0 else "FAIL",
                test_name=test_name,
                stdout_file=stdout_file,
                stderr_file=stderr_file,
                total_trades=int(parsed["total_trades"]),
                wins=int(parsed["wins"]),
                losses=int(parsed["losses"]),
                draws=int(parsed["draws"]),
                win_rate_pct=float(parsed["win_rate_pct"]),
                avg_return_pct=float(parsed["avg_return_pct"]),
                avg_loss_pct=float(parsed["avg_loss_pct"]),
                expectancy_pct=float(parsed["expectancy_pct"]),
                net_pnl=float(parsed["net_pnl"]),
                profit_factor=float(parsed["profit_factor"]),
                avg_holding_min=float(parsed["avg_holding_min"]),
                parse_ok=bool(parsed["parse_ok"]),
                parse_note=str(parsed["parse_note"]),
            )
            rows.append(row)

            print(
                f"[DONE] {case_name} #{run_no} | rc={row.return_code} | "
                f"trades={row.total_trades} wins={row.wins} losses={row.losses} "
                f"net_pnl={row.net_pnl}"
            )

            if args.delay > 0:
                time.sleep(args.delay)

    summary = build_summary(rows)

    csv_path = output_dir / "bulk_run_results.csv"
    json_path = output_dir / "bulk_run_results.json"
    txt_path = output_dir / "bulk_run_report.txt"

    save_csv(csv_path, rows)
    save_json(json_path, rows, summary)
    txt_path.write_text(build_report_text(summary, rows), encoding="utf-8")

    print("=" * 70)
    print("대량 테스트 완료")
    print(f"- CSV : {csv_path}")
    print(f"- JSON: {json_path}")
    print(f"- TXT : {txt_path}")
    if args.log_mode in ("realtime", "end"):
        print(f"- LOGS: {logs_dir}")
    else:
        print("- LOGS: 생성 안함 (log_mode=off)")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
