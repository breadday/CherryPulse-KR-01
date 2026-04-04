# main.py  - 개발용

from broker.kiwoom_stub import KiwoomStubBroker
from strategy.momentum_intraday import MomentumIntradayStrategy
from engine import TradingEngine
from utils.logger import setup_logger
from config_test import STRATEGY_CONFIG


def main():
    logger = setup_logger("CherryPulse-Dev")
    logger.info("개발용 main.py 시작")
    logger.info("실행 모드 | DEV/STUB")

    broker = KiwoomStubBroker()
    strategy = MomentumIntradayStrategy(config=STRATEGY_CONFIG)
    engine = TradingEngine(broker, strategy, logger)

    engine.start()

    # -------------------------
    # 개발용 샘플 틱
    # 전략 튜닝/로그 확인용
    # -------------------------
    raw_ticks = [
        {
            "symbol": "005930",
            "price": 70000,
            "trade_volume": 1000,
            "price_change_pct": 0.3,
            "trade_strength": 105.0,
            "volume_ratio": 0.90,
            "news_score": 0.2,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "005930",
            "price": 70400,
            "trade_volume": 1300,
            "price_change_pct": 0.6,
            "trade_strength": 125.0,
            "volume_ratio": 1.05,
            "news_score": 0.8,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "005930",
            "price": 70800,
            "trade_volume": 1600,
            "price_change_pct": 1.0,
            "trade_strength": 145.0,
            "volume_ratio": 1.20,
            "news_score": 1.2,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "005930",
            "price": 71200,
            "trade_volume": 1900,
            "price_change_pct": 1.4,
            "trade_strength": 160.0,
            "volume_ratio": 1.45,
            "news_score": 1.5,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "005930",
            "price": 70600,
            "trade_volume": 1200,
            "price_change_pct": 0.7,
            "trade_strength": 95.0,
            "volume_ratio": 0.80,
            "news_score": 0.1,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
    ]

    logger.info("개발용 테스트틱 주입 시작")

    for idx, raw_tick in enumerate(raw_ticks, start=1):
        logger.info(
            f"[DEV TICK {idx}] "
            f"symbol={raw_tick['symbol']} "
            f"price={raw_tick['price']} "
            f"chg={raw_tick.get('price_change_pct', 0.0)} "
            f"strength={raw_tick.get('trade_strength', 0.0)} "
            f"vr={raw_tick.get('volume_ratio', 0.0)} "
            f"news={raw_tick.get('news_score', 0.0)}"
        )
        engine.on_real_tick(raw_tick)

    logger.info("개발용 테스트틱 주입 종료")


if __name__ == "__main__":
    main()