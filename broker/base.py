from core.models import Signal, Order


class BaseBroker:
    def connect(self):
        raise NotImplementedError

    def place_order(self, signal: Signal) -> Order:
        raise NotImplementedError

    def is_connected(self) -> bool:
        raise NotImplementedError