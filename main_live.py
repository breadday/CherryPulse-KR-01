# main_live.py

import sys
import os
import signal
import time
from datetime import datetime

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from broker.kiwoom_broker import KiwoomBroker
from data.market_stream import MarketStream
from engine import TradingEngine
from strategy.momentum_intraday import MomentumIntradayStrategy
from utils.logger import setup_logger
from core.models import Signal, Side, OrderType

import config_live as config
from config_live import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, STRATEGY_CONFIG, ACCOUNT_PASSWORD
from infra.telegram_notifier import TelegramNotifier


def is_market_open():
    now = datetime.now().time()
    market_open = datetime.strptime("09:00", "%H:%M").time()
    market_close = datetime.strptime("15:30", "%H:%M").time()
    return market_open <= now <= market_close


def main():
    app = QApplication(sys.argv)

    logger = setup_logger("CherryPulse-Live")
    logger.info("프로그램 시작")

    telegram = None
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        telegram = TelegramNotifier(
            token=TELEGRAM_TOKEN,
            chat_id=TELEGRAM_CHAT_ID,
            logger=logger,
        )

        telegram.debug_identity()
        
        ok = telegram.send_startup_test()
        if ok:
            logger.info("텔레그램 연결 테스트 성공")
        else:
            logger.warning("텔레그램 연결 테스트 실패 | token/chat_id 또는 네트워크 확인 필요")
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

    def inject_test_ticks():
        if shutting_down["flag"]:
            return

        if not config.DRY_RUN:
            logger.info("LIVE 모드에서는 테스트 틱 주입 안 함")
            return

        logger.info("🧪 DRY_RUN 테스트 틱 주입 시작")

        test_ticks = [
            {
                "symbol": "005930",
                "price": 70000,
                "trade_volume": 1000,
                "price_change_pct": 0.8,
                "trade_strength": 130.0,
                "volume_ratio": 0.95,
                "news_score": 0.5,
                "theme_score": 0.0,
                "leader_score": 0.0,
            },
            {
                "symbol": "005930",
                "price": 70800,
                "trade_volume": 1500,
                "price_change_pct": 1.1,
                "trade_strength": 155.0,
                "volume_ratio": 1.15,
                "news_score": 1.0,
                "theme_score": 0.0,
                "leader_score": 0.0,
            },
            {
                "symbol": "005930",
                "price": 71500,
                "trade_volume": 1800,
                "price_change_pct": 1.5,
                "trade_strength": 170.0,
                "volume_ratio": 1.35,
                "news_score": 1.5,
                "theme_score": 0.0,
                "leader_score": 0.0,
            },
            {
                "symbol": "005930",
                "price": 72000,
                "trade_volume": 2000,
                "price_change_pct": 1.8,
                "trade_strength": 180.0,
                "volume_ratio": 1.50,
                "news_score": 2.0,
                "theme_score": 0.0,
                "leader_score": 0.0,
            },
            {
                "symbol": "005930",
                "price": 72300,
                "trade_volume": 2200,
                "price_change_pct": 2.0,
                "trade_strength": 185.0,
                "volume_ratio": 1.65,
                "news_score": 2.0,
                "theme_score": 0.0,
                "leader_score": 0.0,
            },

            # ✅ 강제 손절 확인용
            {
                "symbol": "005930",
                "price": 70000,
                "trade_volume": 2600,
                "price_change_pct": -0.5,
                "trade_strength": 90.0,
                "volume_ratio": 1.20,
                "news_score": 0.0,
                "theme_score": 0.0,
                "leader_score": 0.0,
            },
        ]

        interval_ms = 1000

        def push_tick(index: int):
            if shutting_down["flag"]:
                return

            if index >= len(test_ticks):
                logger.info("🧪 DRY_RUN 테스트 틱 주입 종료")
                return

            tick = test_ticks[index]
            logger.info(
                f"🧪 테스트틱 주입 | symbol={tick['symbol']} "
                f"price={tick['price']} vol={tick['trade_volume']} "
                f"chg={tick.get('price_change_pct', 0.0)} "
                f"strength={tick.get('trade_strength', 0.0)} "
                f"vr={tick.get('volume_ratio', 0.0)}"
            )

            try:
                engine.on_real_tick(tick)
            except Exception as e:
                logger.exception(f"테스트틱 처리 실패 | idx={index} err={e}")
                return

            QTimer.singleShot(interval_ms, lambda: push_tick(index + 1))

        push_tick(0)

    def test_order():
        if shutting_down["flag"]:
            return

        if not config.DRY_RUN and not is_market_open():
            logger.info("장 외 시간 → 주문 스킵")
            return

        if config.DRY_RUN and not is_market_open():
            logger.info("DRY_RUN 장외 테스트 허용 | 테스트 주문 진행")

        logger.info("🔥 테스트 주문 실행")

        signal_obj = Signal(
            symbol="005930",
            side=Side.BUY,
            qty=1,
            price=0,
            order_type=OrderType.MARKET,
            reason="1주 테스트 매수"
        )

        if telegram:
            telegram.send("🔥 테스트 주문 실행")

        order = broker.place_order(signal_obj)

        logger.info(
            f"테스트 주문 결과 | order_id={order.order_id} status={order.status}"
        )

        if telegram:
            telegram.send(
                f"📈 주문 발생\n"
                f"종목: {signal_obj.symbol}\n"
                f"수량: {signal_obj.qty}\n"
                f"상태: {order.status}"
            )

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

    broker.show_account_window()
    logger.info("계좌비밀번호 창에서 저장 후 사용하세요.")

    logger.info("계좌 동기화 시작")

    time.sleep(1.5)
    engine.sync_account(password=ACCOUNT_PASSWORD)

    time.sleep(1.0)
    engine.sync_pending_orders(password=ACCOUNT_PASSWORD)

    engine.health_check()

    stream.subscribe(["005930", "000660"])

    if config.DRY_RUN:
        QTimer.singleShot(3000, inject_test_ticks)
    else:
        QTimer.singleShot(3000, test_order)

    logger.info("실시간 엔진 시작")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()