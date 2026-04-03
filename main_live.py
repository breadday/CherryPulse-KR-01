# main_live.py

import sys
import os
import signal
import time   # ✅ 추가
from datetime import datetime

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from broker.kiwoom_broker import KiwoomBroker
from data.market_stream import MarketStream
from engine import TradingEngine
from strategy.momentum_intraday import MomentumIntradayStrategy
from utils.logger import setup_logger
from core.models import Signal, Side, OrderType

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, STRATEGY_CONFIG, ACCOUNT_PASSWORD
from infra.telegram_notifier import TelegramNotifier

telegram = None

if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    telegram = TelegramNotifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)


# -------------------------
# 장 시간 체크
# -------------------------
def is_market_open():
    now = datetime.now().time()
    market_open = datetime.strptime("09:00", "%H:%M").time()
    market_close = datetime.strptime("15:30", "%H:%M").time()
    return market_open <= now <= market_close


# -------------------------
# 메인
# -------------------------
def main():
    app = QApplication(sys.argv)

    if telegram:
        telegram.send("🚀 자동매매 시작")

    logger = setup_logger("CherryPulse-Live")
    logger.info("프로그램 시작")

    import config

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
        account_no="8122731511"
    )

    strategy = MomentumIntradayStrategy(config=STRATEGY_CONFIG)

    engine = TradingEngine(
        broker,
        strategy,
        logger,
        telegram=telegram
    )

    stream = MarketStream(broker, logger)

    shutting_down = {"flag": False}

    # -------------------------
    # 종료 함수
    # -------------------------
    def shutdown(*args):
        if shutting_down["flag"]:
            return
        shutting_down["flag"] = True

        logger.info("종료 신호 수신")

        try:
            stream.unsubscribe_all()
            logger.info("실시간 구독 해제 완료")
        except Exception as e:
            logger.warning(f"실시간 구독 해제 실패 | {e}")

        try:
            engine.stop()
        except Exception as e:
            logger.warning(f"엔진 종료 실패 | {e}")

        logger.info("프로그램 종료")
        if telegram:
            telegram.send("🛑 자동매매 종료")

        os._exit(0)

    # -------------------------
    # 자동 종료
    # -------------------------
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

    # -------------------------
    # 시그널 등록
    # -------------------------
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    heartbeat = QTimer()
    heartbeat.start(200)
    heartbeat.timeout.connect(lambda: None)

    shutdown_timer = QTimer()
    shutdown_timer.start(60000)
    shutdown_timer.timeout.connect(auto_shutdown)

    # -------------------------
    # 실행
    # -------------------------
    engine.start()

    # 로그인 완료 후 계좌 비밀번호 창
    broker.show_account_window()
    logger.info("계좌비밀번호 창에서 저장 후 사용하세요.")

    # =========================
    # 🔥 핵심 수정 부분
    # =========================
    logger.info("계좌 동기화 시작")

    time.sleep(1.5)
    engine.sync_account(password=ACCOUNT_PASSWORD)

    time.sleep(1.0)
    engine.sync_pending_orders(password=ACCOUNT_PASSWORD)

    engine.health_check()

    # =========================

    stream.subscribe(["005930", "000660"])

    logger.info("실시간 엔진 시작")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()