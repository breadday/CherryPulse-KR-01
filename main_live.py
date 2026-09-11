# -*- coding: utf-8 -*-
# main_live.py
from __future__ import annotations

import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

import config_live as config
from broker.kiwoom_broker import KiwoomBroker
from config_live import (
    ACCOUNT_NO,
    ACCOUNT_PASSWORD,
    SQLITE_DB_PATH,
    STRATEGY_CONFIG,
    STRATEGY_RUNTIME_CONFIG,
    STRATEGY_UNIVERSE_CONFIG,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
)
from engine import TradingEngine
from infra.sqlite_store import SQLiteStore
from infra.telegram_notifier import TelegramNotifier
from strategy.momentum_intraday import MomentumIntradayStrategy
from selectors.external_candidate_provider import ExternalCandidateError
from universe_manager import UniverseManager
from utils.logger import setup_logger

try:
    from _test_force_exit_helper import force_close_all_positions
except ImportError:
    def force_close_all_positions(engine, logger=None, reason="TEST_FORCE_EXIT"):
        if logger:
            logger.warning(
                "test_force_exit_helper 없음 | 강제청산 대체 함수 사용 | closed_count=0"
            )
        return 0


CONDITION_NAME = "주도주_스나이퍼"
CONDITION_SEARCH_START_HHMM = "08:50"
AUTO_SHUTDOWN_HHMM = "15:35"
KIWOOM_SERVER_RESTART_HHMM = "07:00"
KIWOOM_RELOGIN_RESUME_HHMM = "07:05"
CONDITION_RETRY_MS = 60_000
MAX_TELEGRAM_SYMBOLS = 20
SNAPSHOT_FILE = "condition_snapshot.json"
RECONNECT_COOLDOWN_SEC = 60
STALE_REALDATA_SEC = 180
STALE_REALDATA_CHECK_HHMM = "09:05"
TELEGRAM_ALERT_COOLDOWN_SEC = 300
LOGIN_FAILURE_BACKOFF_SEC = 600
SHUTDOWN_WATCHDOG_GRACE_SEC = 30


class MainLiveApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.logger = setup_logger("CherryPulse-Live")
        self.telegram = self._build_telegram()
        self.sqlite_store = SQLiteStore(
            db_path=Path(__file__).resolve().parent / SQLITE_DB_PATH,
            logger=self.logger,
        )
        self.broker = KiwoomBroker(logger=self.logger, account_no=(ACCOUNT_NO or None))
        strategy_config = dict(STRATEGY_CONFIG)
        strategy_config["strategy_runtime_config"] = STRATEGY_RUNTIME_CONFIG
        self.engine = TradingEngine(
            self.broker,
            None,
            self.logger,
            telegram=self.telegram,
            sqlite_store=self.sqlite_store,
            test_name=CONDITION_NAME,
        )

        self.shutting_down = False
        self.condition_started = False
        self.booting = True

        self.universe = UniverseManager(
            snapshot_path=Path(__file__).resolve().parent / SNAPSHOT_FILE,
            fallback_condition_name=CONDITION_NAME,
            strategy_universe_config=STRATEGY_UNIVERSE_CONFIG,
            external_candidate_path=(
                Path(__file__).resolve().parent
                / getattr(config, "EXTERNAL_CANDIDATE_FILE", "external_candidates.json")
                if bool(getattr(config, "ENABLE_EXTERNAL_UNIVERSE", False))
                else None
            ),
        )
        strategy_config["universe_provider"] = self.universe.matches_strategy_universe
        self.strategy = MomentumIntradayStrategy(config=strategy_config)
        self.engine.strategy = self.strategy

        self.heartbeat = QTimer()
        self.shutdown_timer = QTimer()
        self.order_manage_timer = QTimer()
        self.condition_timer = QTimer()

        self.snapshot_path = self.universe.snapshot_path
        self._last_wait_log_hhmm = ""
        self.last_real_tick_received_ts = 0.0
        self.condition_failure_count = 0
        self.last_reconnect_attempt_ts = 0.0
        self.reconnect_in_progress = False
        self.reconnect_blocked_until_ts = 0.0
        self.reconnect_block_log_last_sent_ts: dict[str, float] = {}
        self.reconnect_attempt_count_by_reason: dict[str, int] = {}
        self.telegram_alert_last_sent_ts: dict[str, float] = {}
        self.shutdown_watchdog_thread = None
        self.stale_realdata_last_log_ts = 0.0

    def _build_telegram(self):
        telegram = None
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            telegram = TelegramNotifier(
                token=TELEGRAM_TOKEN,
                chat_id=TELEGRAM_CHAT_ID,
                logger=self.logger,
            )
            try:
                telegram.debug_identity()
            except Exception as e:
                self.logger.warning(f"텔레그램 debug_identity 실패 | {e}")

            try:
                ok = telegram.send_startup_test()
                if ok:
                    self.logger.info("텔레그램 연결 테스트 성공")
                else:
                    self.logger.warning(
                        "텔레그램 연결 테스트 실패 | token/chat_id 또는 네트워크 확인 필요"
                    )
            except Exception as e:
                self.logger.warning(f"텔레그램 시작 테스트 실패 | {e}")
        else:
            self.logger.warning("텔레그램 설정 없음 | TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 확인")
        return telegram

    def _send_telegram(self, text: str):
        if not self.telegram:
            return
        try:
            self.telegram.send(text)
        except Exception as e:
            self.logger.warning(f"텔레그램 전송 실패 | {e}")

    def _send_telegram_throttled(
        self,
        key: str,
        text: str,
        cooldown_sec: int = TELEGRAM_ALERT_COOLDOWN_SEC,
    ):
        now_ts = time.time()
        last_sent_ts = self.telegram_alert_last_sent_ts.get(key, 0.0)
        if now_ts - last_sent_ts < cooldown_sec:
            return

        self.telegram_alert_last_sent_ts[key] = now_ts
        self._send_telegram(text)

    def _msec_until_today_hhmm(self, hhmm: str) -> int:
        now = datetime.now()
        target_time = self._parse_hhmm(hhmm)
        target = now.replace(
            hour=target_time.hour,
            minute=target_time.minute,
            second=0,
            microsecond=0,
        )
        delta_sec = (target - now).total_seconds()
        return max(0, int(delta_sec * 1000))

    def _start_shutdown_watchdog(self):
        if self.shutdown_watchdog_thread and self.shutdown_watchdog_thread.is_alive():
            return

        self.shutdown_watchdog_thread = threading.Thread(
            target=self._shutdown_watchdog_loop,
            name="shutdown-watchdog",
            daemon=True,
        )
        self.shutdown_watchdog_thread.start()
        self.logger.info(
            f"자동 종료 watchdog 시작 | shutdown_at={AUTO_SHUTDOWN_HHMM} "
            f"grace_sec={SHUTDOWN_WATCHDOG_GRACE_SEC}"
        )

    def _shutdown_watchdog_loop(self):
        target_time = self._parse_hhmm(AUTO_SHUTDOWN_HHMM)
        target_dt = datetime.now().replace(
            hour=target_time.hour,
            minute=target_time.minute,
            second=0,
            microsecond=0,
        )

        while not self.shutting_down:
            remain_sec = (target_dt - datetime.now()).total_seconds()
            if remain_sec <= 0:
                break
            time.sleep(min(5.0, remain_sec))

        if self.shutting_down:
            return

        now_hhmm = self._now_hhmm()
        self.logger.warning(
            f"자동 종료 watchdog 작동 | now={now_hhmm} shutdown_at={AUTO_SHUTDOWN_HHMM}"
        )

        try:
            QTimer.singleShot(0, self.auto_shutdown)
        except Exception as e:
            self.logger.warning(f"자동 종료 watchdog 요청 실패 | {e}")

        deadline = time.time() + SHUTDOWN_WATCHDOG_GRACE_SEC
        while time.time() < deadline:
            if self.shutting_down:
                return
            time.sleep(0.5)

        self.logger.error(
            f"자동 종료 watchdog 강제 종료 | grace_sec={SHUTDOWN_WATCHDOG_GRACE_SEC}"
        )
        os._exit(0)

    @staticmethod
    def _now_hhmm() -> str:
        return datetime.now().strftime("%H:%M")

    @staticmethod
    def _parse_hhmm(hhmm: str):
        return datetime.strptime(hhmm, "%H:%M").time()

    def _is_trading_day(self, now_dt: datetime | None = None) -> bool:
        now_dt = now_dt or datetime.now()
        if now_dt.weekday() >= 5:
            return False

        holidays = {
            str(day).strip()
            for day in getattr(config, "MARKET_HOLIDAYS", [])
            if str(day).strip()
        }
        return now_dt.strftime("%Y-%m-%d") not in holidays

    def _market_phase(self, now_dt: datetime | None = None) -> str:
        now_dt = now_dt or datetime.now()
        if not self._is_trading_day(now_dt):
            return "non_trading_day"

        now = now_dt.time()
        start_at = self._parse_hhmm(CONDITION_SEARCH_START_HHMM)
        shutdown_at = self._parse_hhmm(AUTO_SHUTDOWN_HHMM)
        if now < start_at:
            return "pre_open_wait"
        if now >= shutdown_at:
            return "after_close"
        return "market_session"

    def _log_market_phase(self):
        phase = self._market_phase()
        now_hhmm = self._now_hhmm()
        today = datetime.now().strftime("%Y-%m-%d")
        weekday = datetime.now().weekday()
        if phase == "non_trading_day":
            self.logger.info(
                f"휴장일 실행 감지 | date={today} weekday={weekday} "
                f"now={now_hhmm} | 즉시 종료 대상"
            )
        elif phase == "pre_open_wait":
            self.logger.info(
                f"장 시작 전 대기 모드 | now={now_hhmm} "
                f"condition_start={CONDITION_SEARCH_START_HHMM} shutdown_at={AUTO_SHUTDOWN_HHMM}"
            )
        elif phase == "after_close":
            self.logger.info(
                f"장 종료 후 실행 감지 | now={now_hhmm} "
                f"shutdown_at={AUTO_SHUTDOWN_HHMM} | 즉시 종료 대상"
            )
        else:
            self.logger.info(
                f"정규장 세션 모드 | now={now_hhmm} "
                f"condition_start={CONDITION_SEARCH_START_HHMM} shutdown_at={AUTO_SHUTDOWN_HHMM}"
            )

    def _in_kiwoom_restart_window(self) -> bool:
        now = datetime.now().time()
        resume_at = self._parse_hhmm(KIWOOM_RELOGIN_RESUME_HHMM)
        return now < resume_at

    def _warn_kiwoom_restart_window(self):
        if not self._in_kiwoom_restart_window():
            return

        now_hhmm = self._now_hhmm()
        self.logger.warning(
            f"키움 서버 재시작 주의 | now={now_hhmm} "
            f"server_restart={KIWOOM_SERVER_RESTART_HHMM} "
            f"relogin_resume={KIWOOM_RELOGIN_RESUME_HHMM} | "
            f"07:00 이전 실행 시 서버 재시작으로 로그아웃될 수 있고, "
            f"자동 재로그인은 비밀번호 입력 문제로 실패할 수 있습니다."
        )
        self._send_telegram_throttled(
            "kiwoom_restart_window",
            (
                f"키움 서버 재시작 주의\n"
                f"현재시각: {now_hhmm}\n"
                f"서버 재시작: {KIWOOM_SERVER_RESTART_HHMM}\n"
                f"재로그인 재개 권장: {KIWOOM_RELOGIN_RESUME_HHMM}\n"
                f"07:00 이전 실행 시 서버 재시작으로 로그아웃될 수 있으며,\n"
                f"자동 재로그인은 비밀번호 입력 문제로 실패할 수 있습니다."
            ),
            cooldown_sec=30 * 60,
        )

    def _safe_has_position(self, symbol: str) -> bool:
        try:
            pos = self.engine.portfolio.get_position(symbol)
            qty = float(getattr(pos, "qty", 0) or 0)
            return qty > 0
        except Exception:
            return False

    def _safe_has_open_order(self, symbol: str) -> bool:
        try:
            order = self.engine.order_manager.get_open_order_by_symbol(symbol)
            if order is None:
                return False

            remain = getattr(order, "unfilled_qty", None)
            qty = getattr(order, "qty", 0)
            filled_qty = getattr(order, "filled_qty", 0)

            if remain is not None:
                return float(remain or 0) > 0

            return float(qty or 0) > float(filled_qty or 0)
        except Exception:
            return False

    def _open_position_codes(self) -> list[str]:
        try:
            positions = getattr(self.engine.portfolio, "positions", {})
            codes = []
            for symbol, pos in positions.items():
                qty = float(getattr(pos, "qty", 0) or 0)
                if qty > 0:
                    codes.append(str(symbol).strip())
            return sorted({code for code in codes if code})
        except Exception as e:
            self.logger.warning(f"보유 종목 감시 목록 생성 실패 | {e}")
            return []

    def _open_order_codes(self) -> list[str]:
        try:
            orders = getattr(self.engine.order_manager, "orders", {})
            codes = []
            for order in orders.values():
                symbol = str(getattr(order, "symbol", "") or "").strip()
                if not symbol:
                    continue

                remain = getattr(order, "unfilled_qty", None)
                qty = float(getattr(order, "qty", 0) or 0)
                filled_qty = float(getattr(order, "filled_qty", 0) or 0)
                if remain is not None:
                    has_open_qty = float(remain or 0) > 0
                else:
                    has_open_qty = qty > filled_qty

                if has_open_qty:
                    codes.append(symbol)
            return sorted({code for code in codes if code})
        except Exception as e:
            self.logger.warning(f"미체결 종목 감시 목록 생성 실패 | {e}")
            return []

    def _all_watch_codes(self) -> list[str]:
        watch_codes = set(self.universe.all_watch_codes())
        watch_codes.update(self._open_position_codes())
        watch_codes.update(self._open_order_codes())
        return sorted({str(code).strip() for code in watch_codes if str(code).strip()})

    def _format_display_list(
        self,
        codes: Iterable[str],
        limit: int = MAX_TELEGRAM_SYMBOLS,
    ) -> list[str]:
        display = []
        for code in list(codes)[:limit]:
            name = self.broker.get_code_name(code)
            display.append(f"{code}({name})")
        return display

    def _refresh_real_registration(self):
        watch_codes = self._all_watch_codes()
        counts = self.universe.strategy_counts()
        position_codes = self._open_position_codes()
        open_order_codes = self._open_order_codes()
        self.broker.register_real(watch_codes)
        self.logger.info(
            f"실시간 구독 동기화 | total={len(watch_codes)} "
            f"codes={', '.join(self._format_display_list(watch_codes)) if watch_codes else '(empty)'} | "
            f"universes={counts} positions={position_codes} open_orders={open_order_codes}"
        )

    def _log_strategy_universe_summary(self, prefix: str):
        counts = self.universe.strategy_counts()
        external_strategy_counts = {
            strategy: len(self.universe.strategy_source_codes(strategy, "external"))
            for strategy in self.universe.strategy_names
        }
        self.logger.info(
            f"{prefix} | strategy_universes={counts} "
            f"snapshot_count={len(self.universe.snapshot_codes())} "
            f"condition_count={len(self.universe.condition_codes())} "
            f"external_count={len(self.universe.external_codes())} "
            f"external_strategy_counts={external_strategy_counts}"
        )

    def _store_strategy_universe_snapshot(self):
        if not self.sqlite_store:
            return

        trade_date = datetime.now().strftime("%Y-%m-%d")
        for strategy_name in STRATEGY_UNIVERSE_CONFIG.keys():
            universe_name = f"{strategy_name}_universe"
            for source_type in ("snapshot", "condition", "external"):
                rows = [
                    {
                        "symbol": symbol,
                        "name": self.broker.get_code_name(symbol),
                    }
                    for symbol in self.universe.strategy_source_codes(strategy_name, source_type)
                ]
                self.sqlite_store.replace_strategy_universe_snapshot(
                    test_name=CONDITION_NAME,
                    strategy_name=strategy_name,
                    universe_name=universe_name,
                    source_type=source_type,
                    rows=rows,
                    trade_date=trade_date,
                )

    def _should_route_tick(self, symbol: str) -> bool:
        return self.universe.should_route(
            symbol,
            has_position=self._safe_has_position(symbol),
            has_open_order=self._safe_has_open_order(symbol),
        )

    def load_snapshot_and_subscribe(self):
        if not self.snapshot_path.exists():
            self.logger.warning(f"snapshot 파일 없음 | path={self.snapshot_path}")
            return

        try:
            payload, snapshot_rows, clean_codes = self.universe.load_snapshot()
        except Exception as e:
            self.logger.exception(f"snapshot 로드 실패 | path={self.snapshot_path} err={e}")
            return

        if not clean_codes:
            self.logger.warning(f"snapshot 종목 없음 | path={self.snapshot_path}")
            return

        ok, freshness_reason = self._validate_snapshot_freshness(payload)
        if not ok:
            self.universe.replace_snapshot_rows([])
            self.logger.error(
                f"snapshot 최신성 검사 실패 | {freshness_reason} | "
                f"path={self.snapshot_path} | 신규매수 후보를 반영하지 않습니다."
            )
            self._send_telegram_throttled(
                "snapshot_stale",
                (
                    f"snapshot 최신성 검사 실패\n"
                    f"{freshness_reason}\n"
                    f"오래된 일봉 후보라 신규매수 후보를 반영하지 않습니다.\n"
                    f"먼저 일봉 CSV 갱신 후 build_daily_strategy_snapshot을 다시 실행하세요."
                ),
                cooldown_sec=30 * 60,
            )
            self._refresh_real_registration()
            self._store_strategy_universe_snapshot()
            self._log_strategy_universe_summary("오래된 snapshot 제외 후 유니버스")
            return

        self._refresh_real_registration()

        generated_at = self.universe.resolve_snapshot_generated_at(payload)
        source_condition = self.universe.resolve_snapshot_condition_name(payload)
        display_text = ", ".join(self._format_display_list(clean_codes))

        self.sqlite_store.replace_condition_snapshot(
            condition_name=source_condition,
            rows=snapshot_rows,
            source="snapshot_file",
        )

        self.logger.info(
            f"snapshot 로드 완료 | generated_at={generated_at} "
            f"condition_name={source_condition} count={len(clean_codes)} "
            f"codes={display_text if display_text else '(empty)'}"
        )
        for strategy_name, count in self.universe.strategy_counts().items():
            strategy_codes = self.universe.strategy_codes(strategy_name)
            if not strategy_codes:
                continue
            strategy_display = ", ".join(self._format_display_list(strategy_codes, limit=10))
            self.logger.info(
                f"snapshot 전략 후보 | strategy={strategy_name} "
                f"count={count} codes={strategy_display}"
            )
        self._store_strategy_universe_snapshot()
        self._log_strategy_universe_summary("snapshot 반영 후 유니버스")

        self._send_telegram(
            f"전일 snapshot 로드\n"
            f"조건명: {source_condition}\n"
            f"생성시각: {generated_at}\n"
            f"종목수: {len(clean_codes)}\n"
            f"종목: {display_text if display_text else '(없음)'}\n"
            f"전략유니버스: {self.universe.strategy_counts()}"
        )

    def _validate_snapshot_freshness(self, payload: dict):
        max_stale_days = int(getattr(config, "SNAPSHOT_MAX_STALE_DAYS", 1) or 1)
        max_missing_trading_days = int(getattr(config, "SNAPSHOT_MAX_MISSING_TRADING_DAYS", 0) or 0)
        today = datetime.now().date()
        generated_at = str(payload.get("generated_at", "") or "").strip()

        generated_date = None
        if generated_at:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    generated_date = datetime.strptime(generated_at[:19], fmt).date()
                    break
                except Exception:
                    continue

        if generated_date and generated_date > today:
            return False, f"미래 생성일 generated_at={generated_at} today={today}"

        latest_date = None
        latest_data_date = str(payload.get("latest_data_date", "") or "").strip()
        if latest_data_date:
            try:
                latest_date = datetime.strptime(latest_data_date[:10], "%Y-%m-%d").date()
            except Exception:
                latest_date = None

        for item in payload.get("codes", []) or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("last_date", "") or "").strip()
            if not text:
                continue
            try:
                item_date = datetime.strptime(text[:10], "%Y-%m-%d").date()
            except Exception:
                continue
            if latest_date is None or item_date > latest_date:
                latest_date = item_date

        if latest_date is None:
            return False, "후보 last_date 없음"

        if latest_date > today:
            return False, f"미래 일봉 latest_date={latest_date} today={today}"

        calendar_days = (today - latest_date).days
        missing_trading_days = self._count_trading_days_between(latest_date, today)
        if missing_trading_days > max_missing_trading_days:
            return False, (
                f"전일 거래일 데이터 누락 latest_date={latest_date} today={today} "
                f"missing_trading_days={missing_trading_days}>{max_missing_trading_days} "
                f"calendar_days={calendar_days}"
            )

        # 주말이 끼면 달력일수는 3일이어도 거래일 기준으로는 정상입니다.
        trading_stale_days = missing_trading_days
        if trading_stale_days > max_stale_days:
            return False, (
                f"후보 일봉이 오래됨 latest_date={latest_date} today={today} "
                f"trading_stale_days={trading_stale_days}>{max_stale_days} "
                f"calendar_days={calendar_days}"
            )

        return True, (
            f"OK latest_date={latest_date} calendar_days={calendar_days} "
            f"missing_trading_days={missing_trading_days}"
        )

    def _count_trading_days_between(self, start_date, end_date) -> int:
        # start_date 다음 날부터 end_date 전날까지 빠진 거래일 수를 계산합니다.
        # 주말과 config_live.MARKET_HOLIDAYS는 제외합니다.
        holidays = {
            str(day).strip()
            for day in getattr(config, "MARKET_HOLIDAYS", [])
            if str(day).strip()
        }
        count = 0
        cursor = start_date
        while True:
            cursor = cursor.fromordinal(cursor.toordinal() + 1)
            if cursor >= end_date:
                break
            if cursor.weekday() >= 5:
                continue
            if cursor.strftime("%Y-%m-%d") in holidays:
                continue
            count += 1
        return count

    def on_filtered_real_tick(self, raw_tick: dict):
        self.auto_shutdown()
        if self.shutting_down:
            return

        symbol = str(raw_tick.get("symbol", "")).strip()
        if not symbol:
            return

        if not self._should_route_tick(symbol):
            return

        try:
            self.last_real_tick_received_ts = time.time()
            self.engine.on_real_tick(raw_tick)
        except Exception as e:
            self.logger.exception(f"실시간 틱 처리 실패 | symbol={symbol} err={e}")

    def _recover_broker_session(self, reason: str):
        if self.shutting_down or self.reconnect_in_progress:
            return

        now_hhmm = self._now_hhmm()
        # auto_shutdown() runs first from the heartbeat.  Keep this guard for
        # direct callers as well, but do not create an earlier late-session
        # cutoff that leaves positions unwatched before the market closes.
        if now_hhmm >= AUTO_SHUTDOWN_HHMM:
            return

        if self._in_kiwoom_restart_window():
            self.logger.warning(
                f"브로커 세션 복구 보류 | reason={reason} "
                f"relogin_resume={KIWOOM_RELOGIN_RESUME_HHMM}"
            )
            self._send_telegram_throttled(
                "recover_blocked_restart_window",
                (
                    f"브로커 자동 복구 보류\n"
                    f"사유: {reason}\n"
                    f"키움 서버 재시작 구간에는 자동 재로그인을 시도하지 않습니다.\n"
                    f"{KIWOOM_RELOGIN_RESUME_HHMM} 이후 다시 확인해주세요."
                ),
                cooldown_sec=15 * 60,
            )
            return

        now_ts = time.time()
        if now_ts < self.reconnect_blocked_until_ts:
            return

        if now_ts - self.last_reconnect_attempt_ts < RECONNECT_COOLDOWN_SEC:
            return

        reason_key = str(reason or "").split(":", 1)[0]
        max_recoveries = int(getattr(config, "STALE_REALDATA_MAX_RECOVERIES", 3) or 3)
        if reason_key == "stale_realdata":
            current_count = self.reconnect_attempt_count_by_reason.get(reason_key, 0)
            if current_count >= max_recoveries:
                self.reconnect_blocked_until_ts = max(self.reconnect_blocked_until_ts, now_ts + 300)
                self.logger.warning(
                    f"브로커 세션 복구 횟수 초과 보류 | reason={reason} "
                    f"count={current_count}/{max_recoveries} block_sec=300"
                )
                self._send_telegram_throttled(
                    "recover_blocked_max_stale_realdata",
                    (
                        f"브로커 자동 복구 보류\n"
                        f"사유: {reason}\n"
                        f"실시간 틱 무수신 복구가 {max_recoveries}회 반복되어 5분간 추가 복구를 멈춥니다.\n"
                        f"Kiwoom 연결 상태와 실시간 수신 상태를 확인해주세요."
                    ),
                    cooldown_sec=15 * 60,
                )
                return
            self.reconnect_attempt_count_by_reason[reason_key] = current_count + 1

        self.reconnect_in_progress = True
        self.last_reconnect_attempt_ts = now_ts
        self.logger.warning(f"브로커 세션 복구 시도 | reason={reason}")

        try:
            try:
                self.broker.remove_real("ALL")
            except Exception:
                pass

            self.broker.connect()
            time.sleep(1.0)
            self.engine.sync_account(password=ACCOUNT_PASSWORD)
            time.sleep(0.5)
            self.engine.sync_pending_orders(password=ACCOUNT_PASSWORD)
            self.engine.health_check()
            self.load_snapshot_and_subscribe()
            self._refresh_real_registration()

            self.condition_started = False
            self.condition_failure_count = 0
            self.last_real_tick_received_ts = time.time()

            if self._market_phase() == "market_session":
                self.start_condition_search()

            self.logger.info(f"브로커 세션 복구 완료 | reason={reason}")
            self._send_telegram_throttled(
                f"recover_success:{reason}",
                f"브로커 세션 복구 완료\n사유: {reason}",
            )
        except Exception as e:
            self.logger.exception(f"브로커 세션 복구 실패 | reason={reason} err={e}")
            error_text = str(e)
            if "로그인" in error_text or "CommConnect" in error_text or "-101" in error_text:
                self.reconnect_blocked_until_ts = time.time() + LOGIN_FAILURE_BACKOFF_SEC
                self.logger.warning(
                    f"로그인 실패 발생 | 자동 복구 일시 중지 | backoff={LOGIN_FAILURE_BACKOFF_SEC}s"
                )
                self._send_telegram_throttled(
                    "recover_login_failed",
                    (
                        f"브로커 세션 복구 실패\n"
                        f"사유: {reason}\n"
                        f"에러: {e}\n"
                        f"{LOGIN_FAILURE_BACKOFF_SEC}초 동안 자동 복구를 멈춥니다."
                    ),
                    cooldown_sec=LOGIN_FAILURE_BACKOFF_SEC,
                )
            else:
                self._send_telegram_throttled(
                    f"recover_failed:{reason}",
                    f"브로커 세션 복구 실패\n사유: {reason}\n에러: {e}",
                )
        finally:
            self.reconnect_in_progress = False

    def subscribe_initial_condition(self, condition_name: str, codes: list[str]):
        clean_codes = self.universe.replace_condition(codes)
        self._refresh_real_registration()
        condition_rows = [
            {
                "symbol": symbol,
                "name": self.broker.get_code_name(symbol),
            }
            for symbol in clean_codes
        ]
        self.sqlite_store.replace_condition_snapshot(
            condition_name=condition_name,
            rows=condition_rows,
            source="initial_condition",
        )

        display_text = ", ".join(self._format_display_list(clean_codes))

        self.logger.info(
            f"조건검색 초기 편입 반영 | name={condition_name} count={len(clean_codes)} "
            f"codes={display_text if display_text else '(empty)'}"
        )
        self._store_strategy_universe_snapshot()
        self._log_strategy_universe_summary("조건검색 초기 반영 후 유니버스")

        self._send_telegram(
            f"조건검색 초기 편입\n"
            f"조건명: {condition_name}\n"
            f"종목수: {len(clean_codes)}\n"
            f"종목: {display_text if display_text else '(없음)'}\n"
            f"전략유니버스: {self.universe.strategy_counts()}"
        )

    def on_condition_realtime(
        self,
        code: str,
        event_type: str,
        condition_name: str,
        condition_index: int,
    ):
        symbol = str(code).strip()
        event = str(event_type).strip().upper()

        if not symbol:
            return

        name = self.broker.get_code_name(symbol)

        if event == "I":
            already_active = not self.universe.add_condition(symbol)
            self.sqlite_store.record_condition_event(
                condition_name=condition_name,
                symbol=symbol,
                name=name,
                event_type="I",
                condition_index=condition_index,
                source="realtime",
            )
            if not already_active:
                self._refresh_real_registration()

            self.logger.info(
                f"조건검색 편입 | name={condition_name} index={condition_index} "
                f"symbol={symbol}({name}) active_count={len(self.universe.condition_codes())}"
            )
            self._store_strategy_universe_snapshot()
            self._log_strategy_universe_summary("조건검색 편입 후 유니버스")
            self._send_telegram(
                f"조건 편입\n조건명: {condition_name}\n종목: {symbol}({name})\n"
                f"전략유니버스: {self.universe.strategy_counts()}"
            )

            return

        if event == "D":
            self.universe.remove_condition(symbol)
            self.sqlite_store.record_condition_event(
                condition_name=condition_name,
                symbol=symbol,
                name=name,
                event_type="D",
                condition_index=condition_index,
                source="realtime",
            )

            self.logger.info(
                f"조건검색 이탈 | name={condition_name} index={condition_index} "
                f"symbol={symbol}({name}) active_count={len(self.universe.condition_codes())}"
            )
            self._store_strategy_universe_snapshot()
            self._log_strategy_universe_summary("조건검색 이탈 후 유니버스")

            if (
                not self.universe.has_snapshot(symbol)
                and not self._safe_has_position(symbol)
                and not self._safe_has_open_order(symbol)
            ):
                self._refresh_real_registration()

            self._send_telegram(
                f"조건 이탈\n조건명: {condition_name}\n종목: {symbol}({name})\n"
                f"전략유니버스: {self.universe.strategy_counts()}"
            )

    def load_external_candidates_and_subscribe(self):
        if not bool(getattr(config, "ENABLE_EXTERNAL_UNIVERSE", False)):
            self.logger.info("외부 후보 universe 비활성화 | external source를 읽지 않습니다")
            return []

        try:
            candidates = self.universe.load_external_candidates(
                as_of=datetime.now(timezone.utc)
            )
        except ExternalCandidateError as e:
            self.logger.exception(
                f"외부 후보 universe 로드 실패 | path={self.universe.external_candidate_path} err={e}"
            )
            for label, operation in (
                ("실시간 등록", self._refresh_real_registration),
                ("SQLite 저장", self._store_strategy_universe_snapshot),
                (
                    "유니버스 요약",
                    lambda: self._log_strategy_universe_summary(
                        "외부 후보 제외 후 유니버스"
                    ),
                ),
            ):
                try:
                    operation()
                except Exception as cleanup_error:
                    self.logger.warning(
                        f"외부 후보 실패 후 {label} 실패 | err={cleanup_error}"
                    )
            self._send_telegram_throttled(
                "external_universe_load_failed",
                f"외부 후보 universe 로드 실패\n에러: {e}\n외부 후보를 반영하지 않습니다.",
            )
            return []

        strategy_counts = {
            strategy: len(self.universe.strategy_source_codes(strategy, "external"))
            for strategy in self.universe.strategy_names
        }
        self.logger.info(
            f"외부 후보 universe 로드 완료 | count={len(candidates)} "
            f"external_strategy_counts={strategy_counts}"
        )
        self._refresh_real_registration()
        self._store_strategy_universe_snapshot()
        self._log_strategy_universe_summary("외부 후보 반영 후 유니버스")
        return candidates

    def log_run_mode(self):
        self.logger.info("프로그램 시작")
        run_source = "일봉 후보 snapshot 실행" if not bool(getattr(config, "ENABLE_CONDITION_SEARCH", True)) else "snapshot + 조건검색 실행"
        self.logger.info(
            f"{run_source} | condition_name={CONDITION_NAME} | "
            f"condition_search_start={CONDITION_SEARCH_START_HHMM} | "
            f"snapshot_file={self.snapshot_path.name} | "
            f"external_universe={'enabled' if bool(getattr(config, 'ENABLE_EXTERNAL_UNIVERSE', False)) else 'disabled'}"
            + (
                f" external_file={Path(getattr(config, 'EXTERNAL_CANDIDATE_FILE', '')).name}"
                if bool(getattr(config, "ENABLE_EXTERNAL_UNIVERSE", False))
                else ""
            )
        )
        self.logger.info(
            f"실행 모드 | RUN_MODE={getattr(config, 'RUN_MODE', 'paper')} "
            f"PAPER_TRADING={getattr(config, 'PAPER_TRADING', config.DRY_RUN)} "
            f"ALLOW_LIVE_ORDERS={getattr(config, 'ALLOW_LIVE_ORDERS', config.LIVE_MODE)}"
        )

        if getattr(config, "PAPER_TRADING", config.DRY_RUN):
            self.logger.warning("모의투자 모드입니다. 실제 주문은 전송되지 않습니다.")
        elif not getattr(config, "ALLOW_LIVE_ORDERS", config.LIVE_MODE):
            self.logger.warning("실주문 차단 상태입니다. 주문은 모의 처리됩니다.")
        else:
            self.logger.warning("실주문 모드입니다. 실제 주문이 전송됩니다.")
        self._log_market_phase()
        self._warn_kiwoom_restart_window()

    def start_condition_search(self):
        if self.shutting_down:
            return
        if not bool(getattr(config, "ENABLE_CONDITION_SEARCH", True)):
            self.condition_started = True
            self.logger.info("조건검색 비활성화 | 일봉 후보 snapshot만 사용")
            return

        try:
            self.logger.info("조건검색 시작 시도")
            self.broker.load_condition_list()
            codes = self.broker.send_condition_by_name(CONDITION_NAME, search=1)
            self.condition_started = True
            self.condition_failure_count = 0

            if codes:
                self.logger.info(
                    f"조건검색 시작 완료 | name={CONDITION_NAME} initial_count={len(codes)}"
                )
            else:
                self.logger.warning(
                    f"조건검색 초기 결과 비어 있음 | name={CONDITION_NAME} | 재시도 예정"
                )
        except Exception as e:
            self.condition_failure_count += 1
            self.logger.exception(f"조건검색 시작 실패 | condition_name={CONDITION_NAME} err={e}")
            self._send_telegram_throttled(
                "condition_search_start_failed",
                f"조건검색 시작 실패\n조건명: {CONDITION_NAME}\n에러: {e}",
            )

    def maybe_start_condition_search(self):
        self.auto_shutdown()
        if self.shutting_down:
            return
        if self.booting:
            return

        if time.time() < self.reconnect_blocked_until_ts:
            return

        now = datetime.now().time()
        start_at = self._parse_hhmm(CONDITION_SEARCH_START_HHMM)
        current_hhmm = self._now_hhmm()

        if now < start_at:
            if current_hhmm != self._last_wait_log_hhmm:
                self.logger.info(
                    f"장 시작 전 대기 모드 | now={current_hhmm} "
                    f"condition_start={CONDITION_SEARCH_START_HHMM} | 조건검색/실매매 대기"
                )
                self._last_wait_log_hhmm = current_hhmm
            return

        if not self.condition_started:
            self.start_condition_search()
            return

        if not bool(getattr(config, "ENABLE_CONDITION_SEARCH", True)):
            return

        if len(self.universe.condition_codes()) == 0:
            self.logger.info("조건검색 결과 부족 | active_count=0")
            self.start_condition_search()

    def shutdown(self, *_args):
        if self.shutting_down:
            return
        self.shutting_down = True
        # Close the engine action gate before any reconciliation.  Callbacks
        # can race this method, so the main-level flag is not sufficient.
        try:
            self.engine.request_shutdown()
        except Exception as e:
            self.logger.warning(f"엔진 종료 게이트 설정 실패 | {e}")

        self.logger.info("종료 신호 수신")
        self._log_open_positions_before_shutdown()
        # These are deliberately independent.  A failed pending query must
        # not suppress the account query (or vice versa), and none of these
        # paths is allowed to erase an unresolved risk event.
        for name, call in self._shutdown_reconciliation_calls():
            try:
                call()
            except Exception as e:
                self.logger.warning(f"종료 전 {name} 실패 | {e}")

        try:
            self.broker.stop_condition(CONDITION_NAME)
        except Exception as e:
            self.logger.warning(f"조건검색 중지 실패 | {e}")

        try:
            if config.DRY_RUN:
                closed_count = force_close_all_positions(
                    self.engine,
                    logger=self.logger,
                    reason="TEST_FORCE_EXIT",
                )
                self.logger.info(f"종료 전 테스트 강제청산 완료 | closed_count={closed_count}")
                time.sleep(0.5)
        except Exception as e:
            self.logger.warning(f"종료 전 테스트 강제청산 실패 | {e}")

        try:
            self.broker.remove_real("ALL")
            self.logger.info("실시간 구독 해제 완료")
        except Exception as e:
            self.logger.warning(f"실시간 구독 해제 실패 | {e}")

        try:
            self.engine._send_notifications_on_stop = bool(
                getattr(config, "SEND_TELEGRAM_ON_SHUTDOWN", False)
            )
            self.engine.stop()
        except Exception as e:
            self.logger.warning(f"엔진 종료 실패 | {e}")

        self.logger.info("프로그램 종료")
        if getattr(config, "SEND_TELEGRAM_ON_SHUTDOWN", False):
            self._send_telegram("자동매매 종료")
        os._exit(0)

    def _shutdown_reconciliation_calls(self):
        reconciliation = [
            ("risk observation", lambda: self.engine.observe_risk_events(reason="shutdown")),
        ]
        shutdown_phase = self._market_phase()
        if shutdown_phase == "market_session":
            reconciliation.extend(
                [
                    ("pending sync", lambda: self.engine.sync_pending_orders(password=ACCOUNT_PASSWORD)),
                    ("account sync", lambda: self.engine.sync_account(password=ACCOUNT_PASSWORD)),
                ]
            )
        else:
            self.logger.info(
                f"종료 전 계좌/TR 동기화 생략 | phase={shutdown_phase} "
                "장 종료 또는 장외 시간에는 조회하지 않습니다"
            )
        return reconciliation

    def auto_shutdown(self):
        if self.shutting_down:
            return

        if not getattr(config, "AUTO_SHUTDOWN_ENABLED", False):
            return

        now_dt = datetime.now()
        phase = self._market_phase(now_dt)
        now = now_dt.time()
        now_hhmm = self._now_hhmm()
        shutdown_time = self._parse_hhmm(AUTO_SHUTDOWN_HHMM)

        if phase == "non_trading_day":
            self.logger.info(
                f"휴장일 자동 종료 | date={now_dt:%Y-%m-%d} "
                f"weekday={now_dt.weekday()} now={now_hhmm}"
            )
            self.shutdown()
            return

        if now >= shutdown_time:
            self.logger.info(
                f"장 종료 시간 도달 → 자동 종료 | now={now_hhmm} "
                f"shutdown_at={AUTO_SHUTDOWN_HHMM}"
            )
            self.shutdown()

    def on_heartbeat(self):
        # This must precede every observation/reconciliation path: at the
        # shutdown boundary that path is allowed to observe, never act.
        self.auto_shutdown()
        if self.shutting_down:
            return
        # Risk reconciliation/status observation is independent of market phase
        # and stale-tick recovery; it never manufactures a price-based stop.
        try:
            self.engine.observe_risk_events(reason="heartbeat")
            self.engine.manage_pending_orders()
        except Exception as e:
            self.logger.warning(f"하트비트 리스크 관찰 실패 | {e}")

        if self.booting:
            return

        if self._market_phase() != "market_session":
            return

        if time.time() < self.reconnect_blocked_until_ts:
            return

        now_hhmm = self._now_hhmm()

        if now_hhmm >= CONDITION_SEARCH_START_HHMM and not self.condition_started:
            self._recover_broker_session("condition_search_inactive")
            return

        if not getattr(self.broker, "connected", False):
            self._recover_broker_session("broker_disconnected")
            return

        if now_hhmm < STALE_REALDATA_CHECK_HHMM:
            return
        if now_hhmm >= AUTO_SHUTDOWN_HHMM:
            return

        watch_codes = self._all_watch_codes()
        if not watch_codes or self.last_real_tick_received_ts <= 0:
            return

        idle_sec = time.time() - self.last_real_tick_received_ts
        if idle_sec >= STALE_REALDATA_SEC:
            now_ts = time.time()
            if now_ts - self.stale_realdata_last_log_ts < TELEGRAM_ALERT_COOLDOWN_SEC:
                return
            self.stale_realdata_last_log_ts = now_ts
            self.logger.warning(
                f"장중 실시간 틱 무수신 감지 | idle_sec={idle_sec:.1f} watch_count={len(watch_codes)}"
            )
            self._recover_broker_session(f"stale_realdata:{int(idle_sec)}s")

    def _log_open_positions_before_shutdown(self):
        try:
            positions = getattr(self.engine.portfolio, "positions", {})
            open_items = []
            for symbol, pos in positions.items():
                qty = int(getattr(pos, "qty", 0) or 0)
                if qty <= 0:
                    continue
                avg_price = float(getattr(pos, "avg_price", 0.0) or 0.0)
                strategy_name = self.engine._strategy_name_for_symbol(symbol)
                open_items.append((symbol, qty, avg_price, strategy_name))

            if not open_items:
                self.logger.info("종료 전 보유 포지션 없음")
                return

            self.logger.warning(f"종료 전 보유 포지션 존재 | count={len(open_items)}")
            for symbol, qty, avg_price, strategy_name in open_items:
                self.logger.warning(
                    f"종료 전 보유 | symbol={symbol} qty={qty} "
                    f"avg_price={avg_price:.0f} strategy={strategy_name or '-'}"
                )
        except Exception as e:
            self.logger.warning(f"종료 전 보유 포지션 확인 실패 | {e}")

    def boot(self):
        self.log_run_mode()

        self.auto_shutdown()
        if self.shutting_down:
            return

        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        self.broker.set_condition_initial_callback(self.subscribe_initial_condition)
        self.broker.set_condition_realtime_callback(self.on_condition_realtime)

        self.heartbeat.timeout.connect(self.on_heartbeat)
        self.heartbeat.start(200)

        self.shutdown_timer.timeout.connect(self.auto_shutdown)
        self.shutdown_timer.start(10_000)
        shutdown_delay_ms = self._msec_until_today_hhmm(AUTO_SHUTDOWN_HHMM)
        if shutdown_delay_ms > 0:
            QTimer.singleShot(shutdown_delay_ms, self.auto_shutdown)
            self.logger.info(
                f"자동 종료 단발 타이머 등록 | shutdown_at={AUTO_SHUTDOWN_HHMM} "
                f"delay_ms={shutdown_delay_ms}"
            )
        self._start_shutdown_watchdog()

        self.order_manage_timer.timeout.connect(self.engine.manage_pending_orders)
        self.order_manage_timer.start(1_000)

        self.condition_timer.timeout.connect(self.maybe_start_condition_search)
        self.condition_timer.start(CONDITION_RETRY_MS)

        self.engine.start()
        self.broker.set_real_tick_callback(self.on_filtered_real_tick)

        self.broker.show_account_window()
        self.logger.info("계좌비밀번호 창에서 비밀번호를 입력해주세요")
        self.logger.info("계좌 동기화 시작")

        time.sleep(1.5)
        self.engine.sync_account(password=ACCOUNT_PASSWORD)
        self._refresh_real_registration()

        time.sleep(1.0)
        self.engine.sync_pending_orders(password=ACCOUNT_PASSWORD)
        self._refresh_real_registration()

        self.engine.health_check()

        self.load_snapshot_and_subscribe()
        self.load_external_candidates_and_subscribe()
        self.booting = False
        self.maybe_start_condition_search()

        run_mode = "daily_snapshot_only" if not bool(getattr(config, "ENABLE_CONDITION_SEARCH", True)) else "snapshot_plus_condition"
        self.logger.info(f"실시간 엔진 시작 | mode={run_mode}")
        sys.exit(self.app.exec_())


def main():
    MainLiveApp().boot()


if __name__ == "__main__":
    main()
