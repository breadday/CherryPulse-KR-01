from datetime import datetime
from broker.kiwoom_stub import KiwoomStubBroker
from strategy.momentum_intraday import MomentumIntradayStrategy
from engine import TradingEngine
from utils.logger import setup_logger
from config import STRATEGY_CONFIG

def main():
    logger = setup_logger()
    broker = KiwoomStubBroker()
    strategy = MomentumIntradayStrategy(config=STRATEGY_CONFIG)
    engine = TradingEngine(broker, strategy, logger)

    engine.start()

    # -------------------------
    # 테스트용 샘플 틱 실행
    # -------------------------
    raw_ticks = [
        {"symbol": "005930", "price": 70000, "trade_volume": 1000},
        {"symbol": "005930", "price": 70800, "trade_volume": 1500},
        {"symbol": "005930", "price": 71500, "trade_volume": 1800},
        {"symbol": "005930", "price": 72000, "trade_volume": 2000},
        {"symbol": "005930", "price": 70500, "trade_volume": 2200},
    ]

    for raw_tick in raw_ticks:
        engine.on_real_tick(raw_tick)


if __name__ == "__main__":
    main()