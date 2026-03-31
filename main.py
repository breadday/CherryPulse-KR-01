from datetime import datetime
from broker.kiwoom_stub import KiwoomStubBroker
from strategy.momentum_intraday import MomentumIntradayStrategy
from engine import TradingEngine
from core.models import TickData
from utils.logger import setup_logger
from config import STRATEGY_CONFIG

def main():
    logger = setup_logger()
    broker = KiwoomStubBroker()
    strategy = MomentumIntradayStrategy(config=STRATEGY_CONFIG)
    engine = TradingEngine(broker, strategy, logger)

    engine.start()

    ticks = [
        TickData(symbol="005930", price=70000, volume=1000, ts=datetime.now()),
        TickData(symbol="005930", price=70800, volume=1500, ts=datetime.now()),
        TickData(symbol="005930", price=71500, volume=1800, ts=datetime.now()),
        TickData(symbol="005930", price=72000, volume=2000, ts=datetime.now()),
        TickData(symbol="005930", price=70500, volume=2200, ts=datetime.now()),
    ]

    for tick in ticks:
        engine.on_tick(tick)


if __name__ == "__main__":
    main()