# data/market_stream.py

from typing import List


class MarketStream:
    def __init__(self, broker, logger):
        self.broker = broker
        self.logger = logger
        self.codes: List[str] = []

    def subscribe(self, codes: List[str]):
        self.codes = codes[:]
        self.broker.register_real(codes)
        self.logger.info(f"실시간 구독 시작 | {','.join(codes)}")

    def unsubscribe_all(self):
        self.broker.remove_real("ALL")
        self.logger.info("실시간 구독 해제 완료")