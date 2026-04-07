# main.py - 개발용

import time

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
    # 목적:
    # 1) 005930 -> 진입 + 부분익절 확인
    # 2) 000660 -> 진입 + 손절 확인
    #
    # 현재 strategy/momentum_intraday.py 튜닝본 기준으로
    # "너무 이른 약한 틱"이 아니라 "실제로 통과 가능한 강도"로 구성
    # -------------------------
    raw_ticks = [
        # ==================================================
        # [CASE 1] 005930 : 진입 유도
        # 현재 전략은 초반 약한 틱은 잘 안 들어가므로
        # 구조/체결강도/거래량비율이 충분히 붙는 흐름으로 구성
        # ==================================================
        {
            "symbol": "005930",
            "price": 70000,
            "trade_volume": 1100,
            "price_change_pct": 0.4,
            "trade_strength": 112.0,
            "volume_ratio": 0.95,
            "news_score": 0.3,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "005930",
            "price": 70600,
            "trade_volume": 1500,
            "price_change_pct": 0.8,
            "trade_strength": 132.0,
            "volume_ratio": 1.10,
            "news_score": 0.9,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "005930",
            "price": 71300,
            "trade_volume": 1900,
            "price_change_pct": 1.4,
            "trade_strength": 148.0,
            "volume_ratio": 1.30,
            "news_score": 1.2,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "005930",
            "price": 72100,
            "trade_volume": 2400,
            "price_change_pct": 2.0,
            "trade_strength": 165.0,
            "volume_ratio": 1.60,
            "news_score": 1.5,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },

        # ==================================================
        # [CASE 1-1] 005930 : 부분익절 유도
        # 72100 기준 +2% ≈ 73542
        # ==================================================
        {
            "symbol": "005930",
            "price": 73700,
            "trade_volume": 2600,
            "price_change_pct": 3.3,
            "trade_strength": 172.0,
            "volume_ratio": 1.85,
            "news_score": 1.8,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },

        # ==================================================
        # [CASE 1-2] 005930 : 후속 흐름
        # 이미 부분익절이 일어나면 포지션이 정리될 수 있으므로
        # 이후 틱은 참고용
        # ==================================================
        {
            "symbol": "005930",
            "price": 74100,
            "trade_volume": 2100,
            "price_change_pct": 3.8,
            "trade_strength": 168.0,
            "volume_ratio": 1.55,
            "news_score": 1.6,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "005930",
            "price": 73200,
            "trade_volume": 1800,
            "price_change_pct": 2.5,
            "trade_strength": 118.0,
            "volume_ratio": 1.20,
            "news_score": 0.7,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },

        # ==================================================
        # [CASE 2] 000660 : 진입 유도
        # 이 종목도 이전 시나리오는 전략 기준으로 약했으므로 강화
        # ==================================================
        {
            "symbol": "000660",
            "price": 120000,
            "trade_volume": 1200,
            "price_change_pct": 0.5,
            "trade_strength": 118.0,
            "volume_ratio": 1.00,
            "news_score": 0.5,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "000660",
            "price": 121200,
            "trade_volume": 1600,
            "price_change_pct": 0.9,
            "trade_strength": 136.0,
            "volume_ratio": 1.15,
            "news_score": 0.9,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "000660",
            "price": 122400,
            "trade_volume": 2100,
            "price_change_pct": 1.4,
            "trade_strength": 152.0,
            "volume_ratio": 1.35,
            "news_score": 1.1,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },
        {
            "symbol": "000660",
            "price": 123300,
            "trade_volume": 2500,
            "price_change_pct": 1.9,
            "trade_strength": 160.0,
            "volume_ratio": 1.55,
            "news_score": 1.3,
            "theme_score": 0.0,
            "leader_score": 0.0,
        },

        # ==================================================
        # [CASE 2-1] 000660 : 손절 유도
        # 123300 기준 -2% ≈ 120834
        # ==================================================
        {
            "symbol": "000660",
            "price": 120500,
            "trade_volume": 2600,
            "price_change_pct": -0.9,
            "trade_strength": 72.0,
            "volume_ratio": 1.60,
            "news_score": -0.3,
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

        # 로그 가독성용
        time.sleep(0.15)

    logger.info("개발용 테스트틱 주입 종료")


if __name__ == "__main__":
    main()