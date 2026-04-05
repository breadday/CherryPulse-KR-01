# -*- coding: utf-8 -*-
"""
auto_session_manager.py

자동 시작 / 자동 종료 / 손실한도 차단 / 로그 기반 위험 감시 매니저

목적
- 장 시작 전 대기 후 자동매매 본체 자동 실행
- 감시기(monitor_runtime_risk.py) 자동 실행
- 장 종료 시 자동 종료
- 일일 손실 한도 / 연속 손실 / 에러 급증 시 자동 중지
- 텔레그램 알림 지원

권장 사용
1) 작업 스케줄러에서 08:45 실행
2) 이 스크립트가 08:50에 자동매매 시작
3) monitor_runtime_risk.py도 자동 실행
4) 15:30 자동 종료

예시
    python auto_session_manager.py --trade-script main_live.py --monitor-script monitor_runtime_risk.py --log-dir logs
    python auto_session_manager.py --trade-script main_live.py --trade-args --mode dry
    python auto_session_manager.py --trade-script main_live_param.py --trade-args --mode dry --enable-monitor --log-dir logs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Dict, List, Optional

try:
    import requests
except Exception:
    requests = None


RE_PERFORMANCE = re.compile(
    r"\[PERFORMANCE\].*?trades=(?P<trades>\d+).*?wins=(?P<wins>\d+).*?losses=(?P<losses>\d+).*?net_pnl=(?P<net>[-+]?\d+(?:\.\d+)?)"
)
RE_TRADE_CLOSE = re.compile(
    r"\[TRADE_CLOSE\]\s+symbol=(?P<symbol>\S+)\s+result=(?P<result>\S+).*?pnl=(?P<pnl>[-+]?\d+(?:\.\d+)?)"
)
RE_ERROR = re.compile(r"\b(ERROR|Traceback|예외|실패)\b")
RE_PROTECTED = re.compile(r"protected=True|엔진 보호|engine_protected")
RE_TICK = re.compile(r"\[TICK\]")


@dataclass
class SessionState:
    started_at: str = ""
    trade_started: bool = False
    trade_pid: int = 0
    monitor_started: bool = False
    monitor_pid: int = 0
    last_log_path: str = ""
    last_tick_at: str = ""
    total_errors: int = 0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    consecutive_losses: int = 0
    net_pnl: float = 0.0
    engine_protected: bool = False
    stop_reason: str = ""
    alerts_sent: int = 0
    last_trade_result: str = ""
    last_trade_symbol: str = ""


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_hhmm(value: str) -> dtime:
    return datetime.strptime(value.strip(), "%H:%M").time()


def safe_float(v, default=0.0) -> float:
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return default


def safe_int(v, default=0) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return default


def send_telegram(token: str, chat_id: str, text: str, timeout: int = 10) -> bool:
    if not token or not chat_id or requests is None:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def find_latest_log(log_dir: Path) -> Optional[Path]:
    candidates: List[Path] = []
    for p in log_dir.rglob("*.log"):
        try:
            if p.is_file():
                candidates.append(p)
        except Exception:
            pass
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def create_process(
    command: List[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> subprocess.Popen:
    stdout_fp = open(stdout_path, "a", encoding="utf-8")
    stderr_fp = open(stderr_path, "a", encoding="utf-8")
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=stdout_fp,
        stderr=stderr_fp,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


def terminate_process_tree(proc: Optional[subprocess.Popen], name: str) -> None:
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
    except Exception as e:
        print(f"[WARN] {name} 종료 실패 | {e}")


class AutoSessionManager:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.base_dir = Path(args.base_dir).resolve()
        self.trade_script = (self.base_dir / args.trade_script).resolve()
        self.monitor_script = (self.base_dir / args.monitor_script).resolve() if args.monitor_script else None
        self.log_dir = (self.base_dir / args.log_dir).resolve()
        self.session_dir = (self.base_dir / args.session_dir / datetime.now().strftime("%Y%m%d_%H%M%S")).resolve()
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.start_time = parse_hhmm(args.start_time)
        self.stop_time = parse_hhmm(args.stop_time)

        self.trade_proc: Optional[subprocess.Popen] = None
        self.monitor_proc: Optional[subprocess.Popen] = None
        self.log_fp = None
        self.log_pos = 0
        self.state = SessionState()

        self.last_alert_ts: Dict[str, float] = {}
        self.alert_cooldown_sec = 60.0
        self.trade_stdout = self.session_dir / "trade_stdout.txt"
        self.trade_stderr = self.session_dir / "trade_stderr.txt"
        self.monitor_stdout = self.session_dir / "monitor_stdout.txt"
        self.monitor_stderr = self.session_dir / "monitor_stderr.txt"
        self.manager_log = self.session_dir / "manager_log.txt"

    def manager_print(self, text: str) -> None:
        line = f"{now_text()} | {text}"
        print(line)
        with open(self.manager_log, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def alert(self, key: str, text: str) -> None:
        now_ts = time.time()
        last = self.last_alert_ts.get(key, 0.0)
        if now_ts - last < self.alert_cooldown_sec:
            return
        self.last_alert_ts[key] = now_ts
        self.state.alerts_sent += 1
        self.manager_print(f"[ALERT] {text}")
        if self.args.telegram_token and self.args.telegram_chat_id:
            send_telegram(self.args.telegram_token, self.args.telegram_chat_id, text)

    def is_after(self, target: dtime) -> bool:
        return datetime.now().time() >= target

    def is_before(self, target: dtime) -> bool:
        return datetime.now().time() < target

    def wait_until_start(self) -> None:
        self.manager_print(f"자동 시작 대기 | start_time={self.args.start_time}")
        while self.is_before(self.start_time):
            time.sleep(5)

    def start_trade(self) -> None:
        if not self.trade_script.exists():
            raise FileNotFoundError(f"자동매매 스크립트가 없습니다: {self.trade_script}")

        cmd = [self.args.python, str(self.trade_script)]
        if self.args.trade_args:
            cmd.extend(self.args.trade_args)

        self.trade_proc = create_process(
            command=cmd,
            cwd=self.base_dir,
            stdout_path=self.trade_stdout,
            stderr_path=self.trade_stderr,
        )
        self.state.started_at = now_text()
        self.state.trade_started = True
        self.state.trade_pid = self.trade_proc.pid
        self.manager_print(f"자동매매 시작 | pid={self.trade_proc.pid} cmd={' '.join(cmd)}")
        self.alert("trade_start", f"▶ 자동매매 시작 | pid={self.trade_proc.pid}")

    def start_monitor(self) -> None:
        if not self.args.enable_monitor:
            return
        if self.monitor_script is None:
            return
        if not self.monitor_script.exists():
            self.manager_print(f"[WARN] 감시기 스크립트 없음: {self.monitor_script}")
            return

        cmd = [
            self.args.python,
            str(self.monitor_script),
            "--log-dir",
            str(self.log_dir),
            "--latest",
            "--state-path",
            str(self.session_dir / "monitor_state.json"),
            "--max-consecutive-losses",
            str(self.args.max_consecutive_losses),
            "--order-burst-threshold",
            str(self.args.monitor_order_burst_threshold),
            "--no-tick-alert-sec",
            str(self.args.no_tick_alert_sec),
            "--open-position-alert-sec",
            str(self.args.open_position_alert_sec),
            "--pending-order-alert-sec",
            str(self.args.pending_order_alert_sec),
        ]
        if self.args.telegram_token and self.args.telegram_chat_id:
            cmd.extend(["--telegram-token", self.args.telegram_token, "--telegram-chat-id", self.args.telegram_chat_id])

        self.monitor_proc = create_process(
            command=cmd,
            cwd=self.base_dir,
            stdout_path=self.monitor_stdout,
            stderr_path=self.monitor_stderr,
        )
        self.state.monitor_started = True
        self.state.monitor_pid = self.monitor_proc.pid
        self.manager_print(f"감시기 시작 | pid={self.monitor_proc.pid}")
        self.alert("monitor_start", f"👀 감시기 시작 | pid={self.monitor_proc.pid}")

    def connect_latest_log(self) -> None:
        latest = find_latest_log(self.log_dir)
        if latest is None:
            return
        if self.state.last_log_path == str(latest):
            return

        self.state.last_log_path = str(latest)
        if self.log_fp:
            try:
                self.log_fp.close()
            except Exception:
                pass
        self.log_fp = open(latest, "r", encoding="utf-8", errors="replace")
        self.log_fp.seek(0, 2)
        self.log_pos = self.log_fp.tell()
        self.manager_print(f"감시 로그 연결 | {latest}")

    def read_new_lines(self) -> List[str]:
        self.connect_latest_log()
        if not self.log_fp:
            return []

        self.log_fp.seek(self.log_pos)
        lines = self.log_fp.readlines()
        self.log_pos = self.log_fp.tell()
        return lines

    def process_line(self, line: str) -> None:
        if RE_TICK.search(line):
            self.state.last_tick_at = now_text()

        if RE_ERROR.search(line):
            self.state.total_errors += 1
            self.alert("error", f"🚨 에러 감지 | {line.strip()[:180]}")

        if RE_PROTECTED.search(line):
            self.state.engine_protected = True
            self.alert("protected", "🛑 엔진 보호 상태 감지")

        m = RE_TRADE_CLOSE.search(line)
        if m:
            symbol = m.group("symbol")
            result = m.group("result")
            pnl = safe_float(m.group("pnl"))
            self.state.total_trades += 1
            self.state.net_pnl += pnl
            self.state.last_trade_symbol = symbol
            self.state.last_trade_result = result

            if result == "WIN":
                self.state.wins += 1
                self.state.consecutive_losses = 0
            elif result == "LOSS":
                self.state.losses += 1
                self.state.consecutive_losses += 1
                self.alert("loss_trade", f"⚠ 손실 거래 | {symbol} pnl={pnl:.2f}")

        m = RE_PERFORMANCE.search(line)
        if m:
            self.state.total_trades = safe_int(m.group("trades"), self.state.total_trades)
            self.state.wins = safe_int(m.group("wins"), self.state.wins)
            self.state.losses = safe_int(m.group("losses"), self.state.losses)
            self.state.net_pnl = safe_float(m.group("net"), self.state.net_pnl)

    def check_stop_rules(self) -> Optional[str]:
        if self.state.net_pnl <= self.args.max_daily_loss:
            return f"일일 손실 한도 도달 | net_pnl={self.state.net_pnl:.2f}"

        if self.state.consecutive_losses >= self.args.max_consecutive_losses:
            return f"연속 손실 제한 도달 | consecutive_losses={self.state.consecutive_losses}"

        if self.state.total_errors >= self.args.max_error_count:
            return f"에러 누적 한도 도달 | errors={self.state.total_errors}"

        if self.state.engine_protected:
            return "엔진 보호 상태 진입"

        if self.is_after(self.stop_time):
            return f"장 종료 시간 도달 | stop_time={self.args.stop_time}"

        return None

    def save_state(self) -> None:
        state_path = self.session_dir / "session_state.json"
        data = self.state.__dict__.copy()
        data["saved_at"] = now_text()
        state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def print_status(self) -> None:
        win_rate = 0.0
        if self.state.total_trades > 0:
            win_rate = (self.state.wins / self.state.total_trades) * 100.0
        self.manager_print(
            f"[STATUS] trades={self.state.total_trades} wins={self.state.wins} "
            f"losses={self.state.losses} win_rate={win_rate:.2f}% "
            f"net_pnl={self.state.net_pnl:.2f} consecutive_losses={self.state.consecutive_losses} "
            f"errors={self.state.total_errors} last_log={self.state.last_log_path or '(none)'}"
        )

    def stop_all(self, reason: str) -> None:
        self.state.stop_reason = reason
        self.alert("stop_all", f"🛑 세션 종료 | {reason}")
        self.manager_print(f"세션 종료 시작 | reason={reason}")
        terminate_process_tree(self.monitor_proc, "monitor")
        terminate_process_tree(self.trade_proc, "trade")
        self.save_state()
        self.manager_print("세션 종료 완료")

    def run(self) -> int:
        self.manager_print("=" * 70)
        self.manager_print("세션 매니저 시작")
        self.manager_print(f"trade_script={self.trade_script}")
        self.manager_print(f"monitor_script={self.monitor_script}")
        self.manager_print(f"log_dir={self.log_dir}")
        self.manager_print("=" * 70)

        self.wait_until_start()
        self.start_trade()

        # 로그 생성 시간을 조금 기다림
        time.sleep(max(self.args.log_wait_sec, 1))
        self.start_monitor()

        last_status_ts = time.time()

        try:
            while True:
                if self.trade_proc and self.trade_proc.poll() is not None:
                    reason = f"자동매매 프로세스 종료 감지 | rc={self.trade_proc.returncode}"
                    self.stop_all(reason)
                    return 0

                if self.monitor_proc and self.monitor_proc.poll() is not None:
                    self.alert("monitor_exit", f"⚠ 감시기 종료 감지 | rc={self.monitor_proc.returncode}")

                for line in self.read_new_lines():
                    self.process_line(line)

                stop_reason = self.check_stop_rules()
                if stop_reason:
                    self.stop_all(stop_reason)
                    return 0

                if time.time() - last_status_ts >= self.args.status_interval_sec:
                    self.print_status()
                    self.save_state()
                    last_status_ts = time.time()

                time.sleep(self.args.poll_interval)

        except KeyboardInterrupt:
            self.stop_all("사용자 중단")
            return 0
        except Exception as e:
            self.stop_all(f"매니저 예외 | {e}")
            return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="자동 시작/종료/감시 세션 매니저")
    parser.add_argument("--base-dir", type=str, default=".", help="프로젝트 루트")
    parser.add_argument("--python", type=str, default=sys.executable, help="파이썬 실행 경로")
    parser.add_argument("--trade-script", type=str, default="main_live.py", help="자동매매 본체 스크립트")
    parser.add_argument("--trade-args", nargs="*", default=[], help="자동매매 스크립트 추가 인자")
    parser.add_argument("--monitor-script", type=str, default="monitor_runtime_risk.py", help="감시기 스크립트")
    parser.add_argument("--enable-monitor", action="store_true", help="감시기 자동 실행")
    parser.add_argument("--log-dir", type=str, default="logs", help="로그 폴더")
    parser.add_argument("--session-dir", type=str, default="session_runs", help="세션 출력 폴더")
    parser.add_argument("--start-time", type=str, default="08:50", help="자동 시작 시각 HH:MM")
    parser.add_argument("--stop-time", type=str, default="15:30", help="자동 종료 시각 HH:MM")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="로그 폴링 주기(초)")
    parser.add_argument("--status-interval-sec", type=int, default=30, help="상태 출력 주기(초)")
    parser.add_argument("--log-wait-sec", type=int, default=10, help="본체 실행 후 로그 생성 대기 시간(초)")
    parser.add_argument("--max-daily-loss", type=float, default=-30000.0, help="일일 손실 중지 기준")
    parser.add_argument("--max-consecutive-losses", type=int, default=2, help="연속 손실 중지 기준")
    parser.add_argument("--max-error-count", type=int, default=3, help="에러 누적 중지 기준")
    parser.add_argument("--monitor-order-burst-threshold", type=int, default=5, help="감시기 주문 급증 기준")
    parser.add_argument("--no-tick-alert-sec", type=int, default=120, help="틱 정지 경고 기준")
    parser.add_argument("--open-position-alert-sec", type=int, default=300, help="장기 보유 경고 기준")
    parser.add_argument("--pending-order-alert-sec", type=int, default=180, help="미체결 장기 지속 경고 기준")
    parser.add_argument("--telegram-token", type=str, default="", help="텔레그램 토큰")
    parser.add_argument("--telegram-chat-id", type=str, default="", help="텔레그램 chat id")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manager = AutoSessionManager(args)
    return manager.run()


if __name__ == "__main__":
    raise SystemExit(main())
