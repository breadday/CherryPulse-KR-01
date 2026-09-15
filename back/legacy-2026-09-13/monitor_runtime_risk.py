# -*- coding: utf-8 -*-
"""
monitor_runtime_risk.py

실전 운영용 로그/리스크 자동 감시 시스템

목적
- 로그 파일을 실시간 감시
- 주문/체결/에러/손실/포지션 리스크 자동 탐지
- 위험 상황 요약 출력
- 선택적으로 텔레그램 알림 전송
- 장중 DRY_RUN / 모의투자 / 실전 운영 감시 공용

지원 기능
1) 로그 파일 tail -f 방식 감시
2) 에러/예외 즉시 감지
3) 연속 손실 감지
4) 과도한 주문 빈도 감지
5) 미체결/열린 포지션 장기 지속 감지
6) 거래 손익 집계
7) 텔레그램 알림 옵션
8) 상태 스냅샷 JSON 저장

실행 예시
    python monitor_runtime_risk.py --log logs/app.log
    python monitor_runtime_risk.py --log logs/app.log --telegram-token xxx --telegram-chat-id yyy
    python monitor_runtime_risk.py --log-dir logs --latest
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Optional

try:
    import requests
except Exception:
    requests = None


# ---------------------------------------------------------
# 패턴
# ---------------------------------------------------------
RE_TRADE_CLOSE = re.compile(
    r"\[TRADE_CLOSE\]\s+symbol=(?P<symbol>\S+)\s+result=(?P<result>\S+).*?pnl=(?P<pnl>[-+]?\d+(?:\.\d+)?)"
)
RE_PERFORMANCE = re.compile(
    r"\[PERFORMANCE\].*?trades=(?P<trades>\d+)\s+wins=(?P<wins>\d+)\s+losses=(?P<losses>\d+).*?net_pnl=(?P<net>[-+]?\d+(?:\.\d+)?)"
)
RE_ORDER = re.compile(r"(주문 등록|자동매도 주문 등록|\[ORDER_READY\])")
RE_TRADE_OPEN = re.compile(r"\[TRADE_OPEN\]\s+symbol=(?P<symbol>\S+)")
RE_EXIT_CHECK = re.compile(r"\[EXIT_CHECK\]\s+(?P<symbol>\S+)")
RE_ERROR = re.compile(r"\b(ERROR|Traceback|예외|실패)\b")
RE_WARN = re.compile(r"\b(WARNING|경고)\b")
RE_TICK = re.compile(r"\[TICK\]\s+(?P<symbol>\S+)")
RE_FILL = re.compile(r"체결 반영 .*?symbol=(?P<symbol>\S+)\s+side=(?P<side>\S+)")
RE_OPEN_POSITION = re.compile(r"\[POS\]\s+(?P<symbol>\S+)\s+qty=(?P<qty>\d+)")
RE_HEALTH = re.compile(r"health_check 완료 .*?pending_orders=(?P<pending>\d+)")
RE_PENDING_RESTORE = re.compile(r"미체결 주문 복원")
RE_PROTECTED = re.compile(r"protected=True|엔진 보호|engine_protected")
RE_STOP_LOSS = re.compile(r"손절|stop_loss|early_failure_exit|engine_early_stop|early_peak_retrace_exit|engine_peak_retrace_stop", re.IGNORECASE)


# ---------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------
@dataclass
class MonitorState:
    started_at: str
    last_line_at: str = ""
    total_lines: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    total_orders: int = 0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    flats: int = 0
    net_pnl: float = 0.0
    consecutive_losses: int = 0
    last_trade_symbol: str = ""
    last_trade_result: str = ""
    last_trade_pnl: float = 0.0
    last_performance_trades: int = 0
    last_performance_wins: int = 0
    last_performance_losses: int = 0
    last_performance_net_pnl: float = 0.0
    open_positions: Dict[str, int] = field(default_factory=dict)
    pending_orders_last_seen: int = 0
    last_tick_at: str = ""
    last_tick_symbol: str = ""
    engine_protected: bool = False
    active_trade_symbols: Dict[str, str] = field(default_factory=dict)
    alerts_sent: int = 0


# ---------------------------------------------------------
# 유틸
# ---------------------------------------------------------
def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "text": text},
            timeout=timeout,
        )
        return resp.status_code == 200
    except Exception:
        return False


def find_latest_log(log_dir: Path) -> Optional[Path]:
    candidates = []
    for p in log_dir.rglob("*.log"):
        try:
            candidates.append((p.stat().st_mtime, p))
        except Exception:
            pass
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ---------------------------------------------------------
# 모니터
# ---------------------------------------------------------
class RuntimeRiskMonitor:
    def __init__(
        self,
        log_path: Path,
        state_path: Path,
        poll_interval: float,
        telegram_token: str = "",
        telegram_chat_id: str = "",
        max_consecutive_losses: int = 2,
        order_burst_threshold: int = 5,
        order_burst_window_sec: int = 60,
        no_tick_alert_sec: int = 120,
        open_position_alert_sec: int = 300,
        pending_order_alert_sec: int = 180,
        startup_tail_lines: int = 0,
    ):
        self.log_path = log_path
        self.state_path = state_path
        self.poll_interval = poll_interval
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.max_consecutive_losses = max_consecutive_losses
        self.order_burst_threshold = order_burst_threshold
        self.order_burst_window_sec = order_burst_window_sec
        self.no_tick_alert_sec = no_tick_alert_sec
        self.open_position_alert_sec = open_position_alert_sec
        self.pending_order_alert_sec = pending_order_alert_sec
        self.startup_tail_lines = startup_tail_lines

        self.state = MonitorState(started_at=now_text())
        self.order_times: Deque[float] = deque()
        self.error_times: Deque[float] = deque()
        self.warn_times: Deque[float] = deque()
        self.last_position_open_ts: Dict[str, float] = {}
        self.last_pending_seen_ts: Optional[float] = None
        self.last_alert_keys: Dict[str, float] = {}
        self.cooldown_sec = 60.0

    def alert(self, key: str, message: str) -> None:
        now_ts = time.time()
        last_ts = self.last_alert_keys.get(key, 0.0)
        if now_ts - last_ts < self.cooldown_sec:
            return
        self.last_alert_keys[key] = now_ts
        self.state.alerts_sent += 1
        print(f"[ALERT] {message}")
        if self.telegram_token and self.telegram_chat_id:
            send_telegram(self.telegram_token, self.telegram_chat_id, message)

    def save_state(self) -> None:
        payload = asdict(self.state)
        payload["saved_at"] = now_text()
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def process_line(self, line: str) -> None:
        self.state.total_lines += 1
        self.state.last_line_at = now_text()
        now_ts = time.time()

        if RE_ERROR.search(line):
            self.state.total_errors += 1
            self.error_times.append(now_ts)
            self.alert("error", f"🚨 에러 감지 | {line.strip()[:180]}")

        elif RE_WARN.search(line):
            self.state.total_warnings += 1
            self.warn_times.append(now_ts)

        if RE_ORDER.search(line):
            self.state.total_orders += 1
            self.order_times.append(now_ts)

        m = RE_TRADE_OPEN.search(line)
        if m:
            symbol = m.group("symbol")
            self.state.active_trade_symbols[symbol] = now_text()
            self.last_position_open_ts[symbol] = now_ts

        m = RE_FILL.search(line)
        if m:
            symbol = m.group("symbol")
            side = m.group("side")
            side_text = str(side)
            if "BUY" in side_text:
                self.last_position_open_ts[symbol] = now_ts
            elif "SELL" in side_text:
                self.last_position_open_ts.pop(symbol, None)
                self.state.open_positions.pop(symbol, None)
                self.state.active_trade_symbols.pop(symbol, None)

        m = RE_TICK.search(line)
        if m:
            self.state.last_tick_at = now_text()
            self.state.last_tick_symbol = m.group("symbol")

        m = RE_OPEN_POSITION.search(line)
        if m:
            symbol = m.group("symbol")
            qty = safe_int(m.group("qty"))
            self.state.open_positions[symbol] = qty
            if qty > 0 and symbol not in self.last_position_open_ts:
                self.last_position_open_ts[symbol] = now_ts

        m = RE_HEALTH.search(line)
        if m:
            self.state.pending_orders_last_seen = safe_int(m.group("pending"))
            if self.state.pending_orders_last_seen > 0:
                self.last_pending_seen_ts = now_ts

        if RE_PENDING_RESTORE.search(line):
            self.last_pending_seen_ts = now_ts

        if RE_PROTECTED.search(line):
            self.state.engine_protected = True
            self.alert("protected", "🛑 엔진 보호 상태 감지")

        m = RE_TRADE_CLOSE.search(line)
        if m:
            result = m.group("result")
            pnl = safe_float(m.group("pnl"))
            symbol = m.group("symbol")

            self.state.total_trades += 1
            self.state.net_pnl += pnl
            self.state.last_trade_symbol = symbol
            self.state.last_trade_result = result
            self.state.last_trade_pnl = pnl
            self.state.active_trade_symbols.pop(symbol, None)
            self.last_position_open_ts.pop(symbol, None)

            if result == "WIN":
                self.state.wins += 1
                self.state.consecutive_losses = 0
            elif result == "LOSS":
                self.state.losses += 1
                self.state.consecutive_losses += 1
                self.alert("loss_trade", f"⚠️ 손실 거래 | {symbol} pnl={pnl:.2f}")
            else:
                self.state.flats += 1
                self.state.consecutive_losses = 0

        m = RE_PERFORMANCE.search(line)
        if m:
            self.state.last_performance_trades = safe_int(m.group("trades"))
            self.state.last_performance_wins = safe_int(m.group("wins"))
            self.state.last_performance_losses = safe_int(m.group("losses"))
            self.state.last_performance_net_pnl = safe_float(m.group("net"))

    def check_risks(self) -> None:
        now_ts = time.time()

        while self.order_times and now_ts - self.order_times[0] > self.order_burst_window_sec:
            self.order_times.popleft()
        while self.error_times and now_ts - self.error_times[0] > 300:
            self.error_times.popleft()
        while self.warn_times and now_ts - self.warn_times[0] > 300:
            self.warn_times.popleft()

        if len(self.order_times) >= self.order_burst_threshold:
            self.alert(
                "order_burst",
                f"⚠️ 주문 급증 감지 | 최근 {self.order_burst_window_sec}초 주문 {len(self.order_times)}건"
            )

        if self.state.consecutive_losses >= self.max_consecutive_losses:
            self.alert(
                "consecutive_losses",
                f"🛑 연속 손실 감지 | {self.state.consecutive_losses}회 연속 손실"
            )

        if self.state.last_tick_at:
            try:
                last_tick_dt = datetime.strptime(self.state.last_tick_at, "%Y-%m-%d %H:%M:%S")
                no_tick_sec = (datetime.now() - last_tick_dt).total_seconds()
                if no_tick_sec >= self.no_tick_alert_sec:
                    self.alert(
                        "no_tick",
                        f"⚠️ 틱 정지 의심 | 마지막 틱 {int(no_tick_sec)}초 전 | symbol={self.state.last_tick_symbol}"
                    )
            except Exception:
                pass

        for symbol, ts in list(self.last_position_open_ts.items()):
            if now_ts - ts >= self.open_position_alert_sec:
                self.alert(
                    f"open_pos_{symbol}",
                    f"⚠️ 포지션 장기 보유 감지 | {symbol} | {int(now_ts - ts)}초 경과"
                )

        if self.last_pending_seen_ts is not None:
            age = now_ts - self.last_pending_seen_ts
            if age >= self.pending_order_alert_sec and self.state.pending_orders_last_seen > 0:
                self.alert(
                    "pending_long",
                    f"⚠️ 미체결 장기 지속 의심 | pending_orders={self.state.pending_orders_last_seen} | {int(age)}초 경과"
                )

        if len(self.error_times) >= 3:
            self.alert("error_burst", f"🚨 에러 급증 감지 | 최근 5분 에러 {len(self.error_times)}건")

    def print_status(self) -> None:
        win_rate = 0.0
        if self.state.total_trades > 0:
            win_rate = (self.state.wins / self.state.total_trades) * 100.0

        print("-" * 70)
        print(
            f"[STATUS] lines={self.state.total_lines} "
            f"errors={self.state.total_errors} warnings={self.state.total_warnings} "
            f"orders={self.state.total_orders} trades={self.state.total_trades} "
            f"wins={self.state.wins} losses={self.state.losses} "
            f"win_rate={win_rate:.2f}% net_pnl={self.state.net_pnl:.2f} "
            f"open_positions={len(self.last_position_open_ts)} pending={self.state.pending_orders_last_seen} "
            f"alerts={self.state.alerts_sent}"
        )

    def tail_follow(self) -> None:
        if not self.log_path.exists():
            raise FileNotFoundError(f"로그 파일이 없습니다: {self.log_path}")

        with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
            if self.startup_tail_lines > 0:
                lines = f.readlines()
                for line in lines[-self.startup_tail_lines:]:
                    self.process_line(line)
                self.print_status()
                self.save_state()
            else:
                f.seek(0, 2)

            last_status_ts = time.time()

            while True:
                line = f.readline()
                if not line:
                    self.check_risks()
                    if time.time() - last_status_ts >= 10:
                        self.print_status()
                        self.save_state()
                        last_status_ts = time.time()
                    time.sleep(self.poll_interval)
                    continue

                self.process_line(line)
                self.check_risks()


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="실전 운영용 로그/리스크 자동 감시 시스템")
    parser.add_argument("--log", type=str, default="", help="감시할 로그 파일 경로")
    parser.add_argument("--log-dir", type=str, default="logs", help="로그 폴더")
    parser.add_argument("--latest", action="store_true", help="log-dir에서 가장 최신 .log 감시")
    parser.add_argument("--state-path", type=str, default="monitor_state.json", help="상태 JSON 저장 경로")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="로그 폴링 주기(초)")
    parser.add_argument("--max-consecutive-losses", type=int, default=2, help="연속 손실 경고 기준")
    parser.add_argument("--order-burst-threshold", type=int, default=5, help="주문 급증 경고 기준 건수")
    parser.add_argument("--order-burst-window-sec", type=int, default=60, help="주문 급증 판단 구간(초)")
    parser.add_argument("--no-tick-alert-sec", type=int, default=120, help="틱 정지 경고 기준(초)")
    parser.add_argument("--open-position-alert-sec", type=int, default=300, help="포지션 장기보유 경고 기준(초)")
    parser.add_argument("--pending-order-alert-sec", type=int, default=180, help="미체결 장기지속 경고 기준(초)")
    parser.add_argument("--startup-tail-lines", type=int, default=0, help="시작 시 최근 N줄 선반영")
    parser.add_argument("--telegram-token", type=str, default="", help="텔레그램 토큰")
    parser.add_argument("--telegram-chat-id", type=str, default="", help="텔레그램 chat_id")
    return parser.parse_args()


def resolve_log_path(args: argparse.Namespace) -> Path:
    if args.log:
        p = Path(args.log).resolve()
        if not p.exists():
            raise FileNotFoundError(f"지정 로그 파일이 없습니다: {p}")
        return p

    log_dir = Path(args.log_dir).resolve()
    if not log_dir.exists():
        raise FileNotFoundError(f"로그 폴더가 없습니다: {log_dir}")

    latest = find_latest_log(log_dir)
    if latest is None:
        raise FileNotFoundError(f"감시할 .log 파일이 없습니다: {log_dir}")

    return latest.resolve()


def main() -> int:
    args = parse_args()
    log_path = resolve_log_path(args)
    state_path = Path(args.state_path).resolve()

    print("=" * 70)
    print("실전 운영용 로그/리스크 감시 시작")
    print(f"log: {log_path}")
    print(f"state: {state_path}")
    print("=" * 70)

    monitor = RuntimeRiskMonitor(
        log_path=log_path,
        state_path=state_path,
        poll_interval=args.poll_interval,
        telegram_token=args.telegram_token,
        telegram_chat_id=args.telegram_chat_id,
        max_consecutive_losses=args.max_consecutive_losses,
        order_burst_threshold=args.order_burst_threshold,
        order_burst_window_sec=args.order_burst_window_sec,
        no_tick_alert_sec=args.no_tick_alert_sec,
        open_position_alert_sec=args.open_position_alert_sec,
        pending_order_alert_sec=args.pending_order_alert_sec,
        startup_tail_lines=args.startup_tail_lines,
    )
    monitor.tail_follow()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
