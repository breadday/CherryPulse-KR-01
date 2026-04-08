# -*- coding: utf-8 -*-
# main_live.py
from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

import config_live as config
from broker.kiwoom_broker import KiwoomBroker
from engine import TradingEngine
from infra.telegram_notifier import TelegramNotifier
from strategy.momentum_intraday import MomentumIntradayStrategy
from utils.logger import setup_logger
from config_live import (
    ACCOUNT_PASSWORD,
    STRATEGY_CONFIG,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
)

try:
    from test_force_exit_helper import force_close_all_positions
except ImportError:
    def force_close_all_positions(engine, logger=None, reason="TEST_FORCE_EXIT"):
        if logger:
            logger.warning(
                "test_force_exit_helper 없음 | 강제청산 더미 함수 사용 | closed_count=0"
            )
        return 0


CONDITION_NAME = "주도주_스나이퍼"
CONDITION_SEARCH_START_HHMM = "08:50"
AUTO_SHUTDOWN_HHMM = "15:20"
CONDITION_RETRY_MS = 60_000
MAX_TELEGRAM_SYMBOLS = 20
SNAPSHOT_FILE = "condition_snapshot.json"


class CodeUniverse:
    def __init__(self):
        self.active_codes: set[str] = set()

    def replace(self, codes: Iterable[str]) -> list[str]:
        clean = sorted({str(x).strip() for x in codes if str(x).strip()})
        self.active_codes.clear()
        self.active_codes.update(clean)
        return clean

    def add(self, code: str) -> None:
        symbol = str(code).strip()
        if symbol:
            self.active_codes.add(symbol)

    def discard(self, code: str) -> None:
        symbol = str(code).strip()
        if symbol:
            self.active_codes.discard(symbol)

    def contains(self, code: str) -> bool:
        return str(code).strip() in self.active_codes

    def count(self) -> int:
        return len(self.active_codes)

    def snapshot(self) -> list[str]:
        return sorted(self.active_codes)


class MainLiveApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.logger = setup_logger("CherryPulse-Live")
        self.telegram = self._build_telegram()
        self.broker = KiwoomBroker(logger=self.logger, account_no="8122731511")
        self.strategy = MomentumIntradayStrategy(config=STRATEGY_CONFIG)
        self.engine = TradingEngine(
            self.broker,
            self.strategy,
            self.logger,
            telegram=self.telegram,
            test_name=CONDITION_NAME,
        )

        self.shutting_down = False
        self.condition_started = False

        self.snapshot_universe = CodeUniverse()
        self.condition_universe = CodeUniverse()

        self.heartbeat = QTimer()
        self.shutdown_timer = QTimer()
        self.order_manage_timer = QTimer()
        self.condition_timer = QTimer()

        self.snapshot_path = Path(__file__).resolve().parent / SNAPSHOT_FILE
        self._last_wait_log_hhmm = ""

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
                    self.logger.warning("텔레그램 연결 테스트 실패 | token/chat_id 또는 네트워크 확인 필요")
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

    @staticmethod
    def _now_hhmm() -> str:
        return datetime.now().strftime("%H:%M")

    @staticmethod
    def _parse_hhmm(hhmm: str):
        return datetime.strptime(hhmm, "%H:%M").time()

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

    def _all_watch_codes(self) -> list[str]:
        merged = set(self.snapshot_universe.snapshot()) | set(self.condition_universe.snapshot())
        return sorted(merged)

    def _format_display_list(self, codes: Iterable[str], limit: int = MAX_TELEGRAM_SYMBOLS) -> list[str]:
        display = []
        for code in list(codes)[:limit]:
            name = self.broker.get_code_name(code)
            display.append(f"{code}({name})")
        return display

    def _refresh_real_registration(self):
        watch_codes = self._all_watch_codes()
        self.broker.register_real(watch_codes)
        self.logger.info(
            f"실시간 구독 동기화 | total={len(watch_codes)} "
            f"codes={', '.join(self._format_display_list(watch_codes)) if watch_codes else '(empty)'}"
        )

    def _should_route_tick(self, symbol: str) -> bool:
        if self.snapshot_universe.contains(symbol):
            return True
        if self.condition_universe.contains(symbol):
            return True
        if self._safe_has_position(symbol):
            return True
        if self._safe_has_open_order(symbol):
            return True
        return False

    def load_snapshot_and_subscribe(self):
        if not self.snapshot_path.exists():
            self.logger.warning(f"snapshot 파일 없음 | path={self.snapshot_path}")
            return

        try:
            payload = json.loads(self.snapshot_path.read_text(encoding='utf-8'))
        except Exception as e:
            self.logger.exception(f"snapshot 읽기 실패 | path={self.snapshot_path} err={e}")
            return

        codes = []
        for item in payload.get("codes", []):
            if isinstance(item, dict):
                symbol = str(item.get("symbol", "")).strip()
            else:
                symbol = str(item).strip()
            if symbol:
                codes.append(symbol)

        clean_codes = self.snapshot_universe.replace(codes)
        if not clean_codes:
            self.logger.warning(f"snapshot 종목 없음 | path={self.snapshot_path}")
            return

        self._refresh_real_registration()

        generated_at = payload.get("generated_at", "")
        source_condition = payload.get("condition_name", CONDITION_NAME)
        display_text = ", ".join(self._format_display_list(clean_codes))

        self.logger.info(
            f"snapshot 로드 완료 | generated_at={generated_at} "
            f"condition_name={source_condition} count={len(clean_codes)} "
            f"codes={display_text if display_text else '(empty)'}"
        )

        self._send_telegram(
            f"🌙 전일 snapshot 로드\n"
            f"조건식: {source_condition}\n"
            f"생성시각: {generated_at}\n"
            f"종목수: {len(clean_codes)}\n"
            f"종목: {display_text if display_text else '(없음)'}"
        )

    def on_filtered_real_tick(self, raw_tick: dict):
        symbol = str(raw_tick.get("symbol", "")).strip()
        if not symbol:
            return

        if not self._should_route_tick(symbol):
            return

        try:
            self.engine.on_real_tick(raw_tick)
        except Exception as e:
            self.logger.exception(f"조건필터 틱 처리 실패 | symbol={symbol} err={e}")

    def subscribe_initial_condition(self, condition_name: str, codes: list[str]):
        clean_codes = self.condition_universe.replace(codes)
        self._refresh_real_registration()

        display_text = ", ".join(self._format_display_list(clean_codes))

        self.logger.info(
            f"조건검색 초기 편입 반영 | name={condition_name} count={len(clean_codes)} "
            f"codes={display_text if display_text else '(empty)'}"
        )

        self._send_telegram(
            f"🎯 조건검색 초기 편입\n"
            f"조건식: {condition_name}\n"
            f"종목수: {len(clean_codes)}\n"
            f"종목: {display_text if display_text else '(없음)'}"
        )

    def on_condition_realtime(self, code: str, event_type: str, condition_name: str, condition_index: int):
        symbol = str(code).strip()
        event = str(event_type).strip().upper()

        if not symbol:
            return

        name = self.broker.get_code_name(symbol)

        if event == "I":
            already_active = self.condition_universe.contains(symbol)
            self.condition_universe.add(symbol)
            if not already_active:
                self._refresh_real_registration()

            self.logger.info(
                f"조건검색 편입 | name={condition_name} index={condition_index} "
                f"symbol={symbol}({name}) active_count={self.condition_universe.count()}"
            )
            self._send_telegram(
                f"✅ 조건 편입\n조건식: {condition_name}\n종목: {symbol}({name})"
            )
            return

        if event == "D":
            self.condition_universe.discard(symbol)

            self.logger.info(
                f"조건검색 이탈 | name={condition_name} index={condition_index} "
                f"symbol={symbol}({name}) active_count={self.condition_universe.count()}"
            )

            if (
                not self.snapshot_universe.contains(symbol)
                and not self._safe_has_position(symbol)
                and not self._safe_has_open_order(symbol)
            ):
                self._refresh_real_registration()

            self._send_telegram(
                f"⚪ 조건 이탈\n조건식: {condition_name}\n종목: {symbol}({name})"
            )

    def log_run_mode(self):
        self.logger.info("프로그램 시작")
        self.logger.info(
            f"snapshot + 조건검색 실행 | condition_name={CONDITION_NAME} | "
            f"condition_search_start={CONDITION_SEARCH_START_HHMM} | "
            f"snapshot_file={self.snapshot_path.name}"
        )
        self.logger.info(
            f"실행 모드 | DRY_RUN={config.DRY_RUN} LIVE_MODE={config.LIVE_MODE}"
        )

        if config.DRY_RUN:
            self.logger.warning("현재 DRY_RUN 모드입니다. 실제 주문은 전송되지 않습니다.")
        elif not config.LIVE_MODE:
            self.logger.warning("LIVE_MODE=False 상태입니다. 실제 주문은 차단됩니다.")
        else:
            self.logger.warning("실주문 모드입니다. 실제 주문이 전송됩니다.")

    def start_condition_search(self):
        if self.shutting_down:
            return

        try:
            self.logger.info("조건검색 시작 시도")
            self.broker.load_condition_list()
            codes = self.broker.send_condition_by_name(CONDITION_NAME, search=1)
            self.condition_started = True

            if codes:
                self.logger.info(
                    f"조건검색 시작 완료 | name={CONDITION_NAME} initial_count={len(codes)}"
                )
            else:
                self.logger.warning(
                    f"조건검색 초기 결과 비어 있음 | name={CONDITION_NAME} | 재시도 유지"
                )
        except Exception as e:
            self.logger.exception(f"조건검색 시작 실패 | condition_name={CONDITION_NAME} err={e}")
            self._send_telegram(
                f"🚨 조건검색 시작 실패\n조건식: {CONDITION_NAME}\n에러: {e}"
            )

    def maybe_start_condition_search(self):
        if self.shutting_down:
            return

        now = datetime.now().time()
        start_at = self._parse_hhmm(CONDITION_SEARCH_START_HHMM)
        current_hhmm = self._now_hhmm()

        if now < start_at:
            if current_hhmm != self._last_wait_log_hhmm:
                self.logger.info(
                    f"조건검색 시작 대기 | now={current_hhmm} start_at={CONDITION_SEARCH_START_HHMM}"
                )
                self._last_wait_log_hhmm = current_hhmm
            return

        if not self.condition_started:
            self.start_condition_search()
            return

        if self.condition_universe.count() == 0:
            self.logger.info("조건검색 재조회 | active_count=0")
            self.start_condition_search()

    def shutdown(self, *_args):
        if self.shutting_down:
            return
        self.shutting_down = True

        self.logger.info("종료 신호 수신")

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
            self.engine.stop()
        except Exception as e:
            self.logger.warning(f"엔진 종료 실패 | {e}")

        self.logger.info("프로그램 종료")
        self._send_telegram("🛑 자동매매 종료")
        os._exit(0)

    def auto_shutdown(self):
        if self.shutting_down:
            return

        if config.DRY_RUN:
            return

        now = datetime.now().time()
        shutdown_time = self._parse_hhmm(AUTO_SHUTDOWN_HHMM)

        if now >= shutdown_time:
            self.logger.info(f"🛑 장 종료 시간 도달 → 자동 종료 | shutdown_at={AUTO_SHUTDOWN_HHMM}")
            self.shutdown()

    def boot(self):
        self.log_run_mode()

        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        self.broker.set_condition_initial_callback(self.subscribe_initial_condition)
        self.broker.set_condition_realtime_callback(self.on_condition_realtime)

        self.heartbeat.start(200)
        self.heartbeat.timeout.connect(lambda: None)

        self.shutdown_timer.start(60_000)
        self.shutdown_timer.timeout.connect(self.auto_shutdown)

        self.order_manage_timer.start(1_000)
        self.order_manage_timer.timeout.connect(self.engine.manage_pending_orders)

        self.condition_timer.start(CONDITION_RETRY_MS)
        self.condition_timer.timeout.connect(self.maybe_start_condition_search)

        self.engine.start()
        self.broker.set_real_tick_callback(self.on_filtered_real_tick)

        self.broker.show_account_window()
        self.logger.info("계좌비밀번호 창에서 저장 후 사용하세요.")
        self.logger.info("계좌 동기화 시작")

        time.sleep(1.5)
        self.engine.sync_account(password=ACCOUNT_PASSWORD)

        time.sleep(1.0)
        self.engine.sync_pending_orders(password=ACCOUNT_PASSWORD)

        self.engine.health_check()

        self.load_snapshot_and_subscribe()
        self.maybe_start_condition_search()

        self.logger.info("실시간 엔진 시작 | mode=snapshot_plus_condition")
        sys.exit(self.app.exec_())


def main():
    MainLiveApp().boot()


if __name__ == "__main__":
    main()
