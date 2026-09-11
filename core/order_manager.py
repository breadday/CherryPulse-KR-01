# core/order_manager.py

from typing import Dict, Optional
from core.models import Order, OrderStatus


class OrderManager:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.broker_to_local_id: Dict[str, str] = {}  # 실제주문번호 -> 내부주문번호
        self.local_to_broker_id: Dict[str, str] = {}

    # -------------------------
    # 주문 등록
    # -------------------------
    def register(self, order: Order):
        self.orders[order.order_id] = order

    # -------------------------
    # 주문 조회
    # -------------------------
    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

    def resolve_order_id(self, order_id: str) -> str:
        """Legacy helper; production paths must use explicit broker lookup."""
        return self.broker_to_local_id.get(order_id, order_id)

    # -------------------------
    # 미체결 / 진행중 주문 존재 여부
    # -------------------------
    def exists_open_order(self, symbol: str) -> bool:
        for order in self.orders.values():
            if order.symbol == symbol and order.status in {
                OrderStatus.PENDING,
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIAL,
            }:
                return True
        return False

    # -------------------------
    # 종목 기준 가장 최근 open 주문
    # -------------------------
    def get_open_order_by_symbol(self, symbol: str) -> Optional[Order]:
        open_orders = [
            order for order in self.orders.values()
            if order.symbol == symbol and order.status in {
                OrderStatus.PENDING,
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIAL,
            }
        ]

        if not open_orders:
            return None

        open_orders.sort(key=lambda x: x.ts, reverse=True)
        return open_orders[0]

    # -------------------------
    # 종목 기준 가장 최근 open 매도 주문
    # -------------------------
    def get_open_sell_order_by_symbol(self, symbol: str) -> Optional[Order]:
        open_orders = [
            order for order in self.orders.values()
            if order.symbol == symbol
            and str(order.side) in ("SELL", "Side.SELL")
            and order.status in {
                OrderStatus.PENDING,
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIAL,
            }
        ]

        if not open_orders:
            return None

        open_orders.sort(key=lambda x: x.ts, reverse=True)
        return open_orders[0]

    # -------------------------
    # 실제 주문번호 매핑
    # -------------------------
    def bind_broker_order_id(self, local_order_id: str, broker_order_id: str,
                             risk_event_id: str = "") -> Optional[Order]:
        local = str(local_order_id or "").strip()
        broker = str(broker_order_id or "").strip()
        event = str(risk_event_id or "").strip()
        if not local or not broker or local == broker:
            return None
        order = self.orders.get(local)
        if order is None:
            return None
        order_event = str(getattr(order, "risk_event_id", "") or "")
        if event and (getattr(order, "purpose", "") != "RISK_STOP" or order_event != event):
            return None
        if order_event and event and order_event != event:
            return None
        existing_local = self.broker_to_local_id.get(broker)
        existing_broker = self.local_to_broker_id.get(local)
        field_broker = str(getattr(order, "broker_order_id", "") or "")
        if existing_local not in (None, local) or existing_broker not in (None, broker) or field_broker not in ("", broker):
            return None
        if existing_local is not None and self.local_to_broker_id.get(existing_local) != broker:
            return None
        if existing_broker is not None and self.broker_to_local_id.get(existing_broker) != local:
            return None
        self.local_to_broker_id[local] = broker
        self.broker_to_local_id[broker] = local
        order.broker_order_id = broker
        return order

    def get_order_by_broker_id(self, broker_order_id: str) -> Optional[Order]:
        broker = str(broker_order_id or "").strip()
        if not broker:
            return None
        local = self.broker_to_local_id.get(broker)
        if not local or self.local_to_broker_id.get(local) != broker:
            return None
        order = self.orders.get(local)
        if order is None or str(getattr(order, "broker_order_id", "") or "") != broker:
            return None
        if sum(1 for value in self.broker_to_local_id.values() if value == local) != 1:
            return None
        return order

    def get_open_risk_sell_order_by_event(self, event_id: str) -> Optional[Order]:
        event = str(event_id or "").strip()
        if not event:
            return None
        candidates = [o for o in self.orders.values()
                      if getattr(o, "purpose", "") == "RISK_STOP"
                      and str(getattr(o, "risk_event_id", "") or "") == event
                      and str(getattr(o.side, "value", o.side)) == "SELL"
                      and o.status in {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL}]
        return candidates[0] if len(candidates) == 1 else None

    # -------------------------
    # 체결 반영
    # -------------------------
    def apply_fill(
        self,
        order_id: str,
        fill_qty: int,
        fill_price: float,
        unfilled_qty: Optional[int] = None,
    ) -> Optional[Order]:
        order = self.orders.get(order_id)
        if order is None:
            return None

        prev_filled = int(getattr(order, "filled_qty", 0) or 0)
        new_filled = prev_filled + int(fill_qty)

        order.filled_qty = new_filled
        order.avg_fill_price = float(fill_price)

        total_qty = int(getattr(order, "qty", 0) or 0)

        if unfilled_qty is not None:
            remain_qty = int(unfilled_qty)
        else:
            remain_qty = max(total_qty - new_filled, 0)

        if remain_qty <= 0:
            order.status = OrderStatus.FILLED
        elif new_filled > 0:
            order.status = OrderStatus.PARTIAL
        else:
            order.status = OrderStatus.SUBMITTED

        return order

