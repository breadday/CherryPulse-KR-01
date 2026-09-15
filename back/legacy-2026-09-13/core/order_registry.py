# core/order_registry.py
from dataclasses import dataclass, field
from typing import Dict, Optional
import time


@dataclass
class OrderRecord:
    request_id: str
    code: str
    side: str              # BUY / SELL
    order_type: str        # MARKET / LIMIT / CANCEL
    qty: int
    price: float
    strategy_tag: str = ""
    parent_order_no: str = ""
    order_no: str = ""
    status: str = "REQUESTED"   # REQUESTED / ACCEPTED / PARTIAL / FILLED / CANCELED / REJECTED
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    remain_qty: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def apply_fill(self, fill_qty: int, fill_price: float):
        prev_cost = self.avg_fill_price * self.filled_qty
        new_cost = prev_cost + (fill_price * fill_qty)
        self.filled_qty += fill_qty

        if self.filled_qty > 0:
            self.avg_fill_price = new_cost / self.filled_qty

        self.remain_qty = max(0, self.qty - self.filled_qty)
        self.updated_at = time.time()

        if self.filled_qty == 0:
            self.status = "ACCEPTED"
        elif self.remain_qty > 0:
            self.status = "PARTIAL"
        else:
            self.status = "FILLED"


class OrderRegistry:
    def __init__(self):
        self.by_request_id: Dict[str, OrderRecord] = {}
        self.by_order_no: Dict[str, OrderRecord] = {}

    def register_request(
        self,
        request_id: str,
        code: str,
        side: str,
        order_type: str,
        qty: int,
        price: float,
        strategy_tag: str = "",
        parent_order_no: str = ""
    ):
        rec = OrderRecord(
            request_id=request_id,
            code=code,
            side=side,
            order_type=order_type,
            qty=qty,
            price=price,
            remain_qty=qty,
            strategy_tag=strategy_tag,
            parent_order_no=parent_order_no,
        )
        self.by_request_id[request_id] = rec
        return rec

    def bind_order_no(self, request_id: str, order_no: str):
        rec = self.by_request_id.get(request_id)
        if not rec:
            return None
        rec.order_no = order_no
        rec.status = "ACCEPTED"
        rec.updated_at = time.time()
        self.by_order_no[order_no] = rec
        return rec

    def get_by_order_no(self, order_no: str) -> Optional[OrderRecord]:
        return self.by_order_no.get(order_no)

    def get_by_request_id(self, request_id: str) -> Optional[OrderRecord]:
        return self.by_request_id.get(request_id)

    def mark_rejected(self, request_id: str):
        rec = self.by_request_id.get(request_id)
        if rec:
            rec.status = "REJECTED"
            rec.updated_at = time.time()

    def mark_canceled(self, order_no: str):
        rec = self.by_order_no.get(order_no)
        if rec:
            rec.status = "CANCELED"
            rec.updated_at = time.time()

    def apply_fill(self, order_no: str, fill_qty: int, fill_price: float) -> Optional[OrderRecord]:
        rec = self.by_order_no.get(order_no)
        if not rec:
            return None
        rec.apply_fill(fill_qty, fill_price)
        return rec