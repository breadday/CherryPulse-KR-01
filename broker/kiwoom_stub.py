import uuid
from core.models import Order, OrderStatus, Signal
from broker.base import BaseBroker


class KiwoomStubBroker(BaseBroker):
    def __init__(self):
        self.connected = False

    def connect(self):
        self.connected = True

    def is_connected(self) -> bool:
        return self.connected

    def place_order(self, signal: Signal) -> Order:
        order = Order(
            order_id=str(uuid.uuid4())[:8],
            symbol=signal.symbol,
            side=signal.side,
            qty=signal.qty,
            price=signal.price,
            order_type=signal.order_type,
            status=OrderStatus.SUBMITTED,
            reason=signal.reason,
        )
        return order