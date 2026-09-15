# core/order_manager.py

from typing import Dict, Optional
from core.models import Order, OrderStatus


class OrderManager:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.broker_to_local_id: Dict[str, str] = {}  # 실제주문번호 -> 내부주문번호

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
    def bind_broker_order_id(self, symbol: str, broker_order_id: str) -> Optional[str]:
        if not broker_order_id:
            return None

        if broker_order_id in self.broker_to_local_id:
            return self.broker_to_local_id[broker_order_id]

        order = self.get_open_order_by_symbol(symbol)
        if order is None:
            return None

        self.broker_to_local_id[broker_order_id] = order.order_id
        return order.order_id

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

