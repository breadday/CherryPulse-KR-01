# -*- coding: utf-8 -*-
# main_live.py
"""
주도주_스나이퍼 조건검색 편입 종목만 자동 매수하도록 만든 실행 파일.
- 고정 종목 subscribe 제거
- 실시간 조건검색 편입(I) 종목만 엔진에 전달
- 조건 이탈(D) 종목은 신규 진입만 차단하고,
  이미 보유 중인 종목은 청산 관리를 위해 틱을 계속 전달
- LIVE 모드에서 3초 뒤 테스트 주문 넣던 로직 제거
"""

import os
import signal
import sys
import time
from datetime import datetime

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

import config_live as config
from broker.kiwoom_broker import KiwoomBroker
from core.models import Side
from engine import TradingEngine
from infra.telegram_notifier import TelegramNotifier
from strategy.momentum_intraday import MomentumIntradayStrategy
from test_force_exit_helper import force_close_all_positions
from utils.logger import setup_logger
from config_live import (
    ACCOUNT_PASSWORD,
    STRATEGY_CONFIG,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
)

CONDITION_NAME = "주도주_스나이퍼"


def is_market_open():
    now = datetime.now().time()
    market_open = datetime.strptime("09:00", "%H:%M").time()
    market_close = datetime.strptime("15:30", "%H:%M").time()
    return market_open <= now <= market_close


def _safe_has_position(engine: TradingEngine, symbol: str) -> bool:
    try:
        pos = engine.portfolio.get_position(symbol)
        qty = float(getattr(pos, "qty", 0) or 0)
        return qty > 0
    except Exception:
        return False


def _safe_has_open_order(engine: TradingEngine, symbol: str) -> bool:
    try:
        order = engine.order_manager.get_open_order_by_symbol(symbol)
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


def main():
    app = QApplication(sys.argv)

    logger = setup_logger("CherryPulse-Live")
    logger.info("프로그램 시작")
    logger.info(f"조건검색 기반 실행 | condition_name={CONDITION_NAME}")

    telegram = None
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        telegram = TelegramNotifier(
            token=TELEGRAM_TOKEN,
            chat_id=TELEGRAM_CHAT_ID,
            logger=logger,
        )
        try:
            telegram.debug_identity()
        except Exception as e:
            logger.warning(f"텔레그램 debug_identity 실패 | {e}")

        try:
            ok = telegram.send_startup_test()
            if ok:
                logger.info("텔레그램 연결 테스트 성공")
            else:
                logger.warning("텔레그램 연결 테스트 실패 | token/chat_id 또는 네트워크 확인 필요")
        except Exception as e:
            logger.warning(f"텔레그램 시작 테스트 실패 | {e}")
    else:
        logger.warning("텔레그램 설정 없음 | TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 확인")

    logger.info(
        f"실행 모드 | DRY_RUN={config.DRY_RUN} LIVE_MODE={config.LIVE_MODE}"
    )

    if config.DRY_RUN:
        logger.warning("현재 DRY_RUN 모드입니다. 실제 주문은 전송되지 않습니다.")
    elif not config.LIVE_MODE:
        logger.warning("LIVE_MODE=False 상태입니다. 실제 주문은 차단됩니다.")
    else:
        logger.warning("실주문 모드입니다. 실제 주문이 전송됩니다.")

    broker = KiwoomBroker(
        logger=logger,
        account_no="8122731511",
    )

    strategy = MomentumIntradayStrategy(config=STRATEGY_CONFIG)

    engine = TradingEngine(
        broker,
        strategy,
        logger,
        telegram=telegram,
        test_name=CONDITION_NAME,
    )

    shutting_down = {"flag": False}
    active_condition_codes = set()
    ever_seen_codes = set()
    dropped_codes = set()

    def should_route_tick(symbol: str) -> bool:
        if symbol in active_condition_codes:
            return True
        if _safe_has_position(engine, symbol):
            return True
        if _safe_has_open_order(engine, symbol):
            return True
        return False

    def on_filtered_real_tick(raw_tick: dict):
        symbol = str(raw_tick.get("symbol", "")).strip()
        if not symbol:
            return

        if not should_route_tick(symbol):
            return

        try:
            engine.on_real_tick(raw_tick)
        except Exception as e:
            logger.exception(f"조건필터 틱 처리 실패 | symbol={symbol} err={e}")

    def subscribe_initial_condition(condition_name: str, codes: list[str]):
        clean_codes = sorted({str(x).strip() for x in codes if str(x).strip()})
        active_condition_codes.clear()
        active_condition_codes.update(clean_codes)
        ever_seen_codes.update(clean_codes)

        broker.register_real(clean_codes)

        logger.info(
            f"조건검색 초기 편입 반영 | name={condition_name} count={len(clean_codes)} "
            f"codes={','.join(clean_codes) if clean_codes else '(empty)'}"
        )

        if telegram:
            try:
                telegram.send(
                    f"🎯 조건검색 초기 편입\n"
                    f"조건식: {condition_name}\n"
                    f"종목수: {len(clean_codes)}\n"
                    f"종목: {', '.join(clean_codes[:20]) if clean_codes else '(없음)'}"
                )
            except Exception as e:
                logger.warning(f"텔레그램 초기 편입 전송 실패 | {e}")

    def on_condition_realtime(code: str, event_type: str, condition_name: str, condition_index: int):
        symbol = str(code).strip()
        event = str(event_type).strip()

        if not symbol:
            return

        if event == "I":
            active_condition_codes.add(symbol)
            ever_seen_codes.add(symbol)
            dropped_codes.discard(symbol)
            broker.register_real_add(symbol)

            logger.info(
                f"조건검색 편입 | name={condition_name} index={condition_index} symbol={symbol} "
                f"active_count={len(active_condition_codes)}"
            )

            if telegram:
                try:
                    telegram.send(
                        f"✅ 조건 편입\n"
                        f"조건식: {condition_name}\n"
                        f"종목: {symbol}"
                    )
                except Exception as e:
                    logger.warning(f"텔레그램 편입 전송 실패 | {e}")

            return

        if event == "D":
            active_condition_codes.discard(symbol)
            dropped_codes.add(symbol)

            logger.info(
                f"조건검색 이탈 | name={condition_name} index={condition_index} symbol={symbol} "
                f"active_count={len(active_condition_codes)}"
            )

            # 이미 보유/미체결이면 실시간은 유지
            if not _safe_has_position(engine, symbol) and not _safe_has_open_order(engine, symbol):
                broker.register_real_remove(symbol)

            if telegram:
                try:
                    telegram.send(
                        f"⚪ 조건 이탈\n"
                        f"조건식: {condition_name}\n"
                        f"종목: {symbol}"
                    )
                except Exception as e:
                    logger.warning(f"텔레그램 이탈 전송 실패 | {e}")

    def shutdown(*_args):
        if shutting_down["flag"]:
            return
        shutting_down["flag"] = True

        logger.info("종료 신호 수신")

        try:
            broker.stop_condition(CONDITION_NAME)
        except Exception as e:
            logger.warning(f"조건검색 중지 실패 | {e}")

        try:
            if config.DRY_RUN:
                closed_count = force_close_all_positions(
                    engine,
                    logger=logger,
                    reason="TEST_FORCE_EXIT",
                )
                logger.info(f"종료 전 테스트 강제청산 완료 | closed_count={closed_count}")
                time.sleep(0.5)
        except Exception as e:
            logger.warning(f"종료 전 테스트 강제청산 실패 | {e}")

        try:
            broker.remove_real("ALL")
            logger.info("실시간 구독 해제 완료")
        except Exception as e:
            logger.warning(f"실시간 구독 해제 실패 | {e}")

        try:
            engine.stop()
        except Exception as e:
            logger.warning(f"엔진 종료 실패 | {e}")

        logger.info("프로그램 종료")
        if telegram:
            try:
                telegram.send("🛑 자동매매 종료")
            except Exception:
                pass

        os._exit(0)

    def auto_shutdown():
        if shutting_down["flag"]:
            return

        if config.DRY_RUN:
            return

        now = datetime.now().time()
        shutdown_time = datetime.strptime("15:20", "%H:%M").time()

        if now >= shutdown_time:
            logger.info("🛑 장 종료 시간 도달 → 자동 종료")
            shutdown()

    def start_condition_search():
        if shutting_down["flag"]:
            return

        try:
            broker.load_condition_list()
            codes = broker.send_condition_by_name(CONDITION_NAME, search=1)
            subscribe_initial_condition(CONDITION_NAME, codes)
        except Exception as e:
            logger.exception(f"조건검색 시작 실패 | condition_name={CONDITION_NAME} err={e}")
            if telegram:
                try:
                    telegram.send(
                        f"🚨 조건검색 시작 실패\n"
                        f"조건식: {CONDITION_NAME}\n"
                        f"에러: {e}"
                    )
                except Exception:
                    pass

    # 콜백 연결
    broker.set_condition_initial_callback(subscribe_initial_condition)
    broker.set_condition_realtime_callback(on_condition_realtime)

    # engine.start()가 broker real tick callback을 engine.on_real_tick으로 설정하므로,
    # 엔진 시작 후 조건필터 래퍼로 한 번 더 덮어쓴다.
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    heartbeat = QTimer()
    heartbeat.start(200)
    heartbeat.timeout.connect(lambda: None)

    shutdown_timer = QTimer()
    shutdown_timer.start(60000)
    shutdown_timer.timeout.connect(auto_shutdown)

    order_manage_timer = QTimer()
    order_manage_timer.start(1000)
    order_manage_timer.timeout.connect(engine.manage_pending_orders)

    engine.start()
    broker.set_real_tick_callback(on_filtered_real_tick)

    broker.show_account_window()
    logger.info("계좌비밀번호 창에서 저장 후 사용하세요.")
    logger.info("계좌 동기화 시작")

    time.sleep(1.5)
    engine.sync_account(password=ACCOUNT_PASSWORD)

    time.sleep(1.0)
    engine.sync_pending_orders(password=ACCOUNT_PASSWORD)

    engine.health_check()

    # 기존 main_live의 고정종목 subscribe / 실전 테스트주문은 제거하고
    # 조건검색 기반 구독만 시작한다.
    QTimer.singleShot(1000, start_condition_search)

    logger.info("실시간 엔진 시작 | mode=condition_only")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
