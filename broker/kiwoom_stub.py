import uuid
from core.models import Order, OrderStatus, Signal
from broker.base import BaseBroker


class KiwoomStubBroker(BaseBroker):
    def __init__(self):
        self.connected = False
        self.real_tick_callback = None
        self.fill_callback = None
        self.msg_callback = None

    def set_real_tick_callback(self, callback):
        self.real_tick_callback = callback

    def set_fill_callback(self, callback):
        self.fill_callback = callback

    def set_msg_callback(self, callback):
        self.msg_callback = callback

    def get_deposit(self, password: str = ""):
        return {"available_cash": 0}

    def get_positions(self, password: str = ""):
        return {"positions": []}

    def get_balance(self):
        return {}

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def shutdown(self):
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def cancel_order(self, symbol: str, order_no: str, qty: int):
        if self.msg_callback is not None:
            self.msg_callback(f"[STUB] 주문 취소: {symbol} order_no={order_no} qty={qty}")
        return 0

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

        if self.msg_callback is not None:
            self.msg_callback(f"[STUB] 주문 접수: {signal.symbol} {signal.side} {signal.qty}주")

        return order