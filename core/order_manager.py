# core/order_manager.py

from typing import Dict, Optional
from core.models import Order, OrderStatus


class OrderManager:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.broker_to_local_id: Dict[str, str] = {}  # 실제주문번호 -> 내부주문번호

    def register(self, order: Order):
        self.orders[order.order_id] = order

    def exists_open_order(self, symbol: str) -> bool:
        for order in self.orders.values():
            if order.symbol == symbol and order.status in {
                OrderStatus.PENDING,
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIAL,
            }:
                return True
        return False

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

    def resolve_order_id(self, order_id: str) -> str:
        return self.broker_to_local_id.get(order_id, order_id)

    def get_order(self, order_id: str) -> Optional[Order]:
        resolved_id = self.resolve_order_id(order_id)
        return self.orders.get(resolved_id)

    def update_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_qty: int | None = None,
        avg_fill_price: float | None = None
    ):
        resolved_id = self.resolve_order_id(order_id)

        if resolved_id not in self.orders:
            return

        order = self.orders[resolved_id]
        order.status = status

        if filled_qty is not None:
            order.filled_qty = filled_qty

        if avg_fill_price is not None:
            order.avg_fill_price = avg_fill_price

    def apply_fill(
        self,
        order_id: str,
        fill_qty: int,
        fill_price: float,
        unfilled_qty: int | None = None
    ) -> Optional[Order]:
        """
        단위 체결(증분 체결)을 누적 반영
        """
        resolved_id = self.resolve_order_id(order_id)

        if resolved_id not in self.orders:
            return None

        order = self.orders[resolved_id]

        prev_filled = order.filled_qty
        new_filled = prev_filled + fill_qty

        # 가중평균 체결가
        if new_filled > 0:
            order.avg_fill_price = (
                (order.avg_fill_price * prev_filled) + (fill_price * fill_qty)
            ) / new_filled

        order.filled_qty = new_filled

        if unfilled_qty is None:
            remain = max(order.qty - order.filled_qty, 0)
        else:
            remain = max(unfilled_qty, 0)

        if order.filled_qty <= 0:
            order.status = OrderStatus.SUBMITTED
        elif remain > 0:
            order.status = OrderStatus.PARTIAL
        else:
            order.status = OrderStatus.FILLED

        return order
    
    def get_open_orders_by_symbol(self, symbol: str):
        result = []
        for order in self.orders.values():
            if order.symbol == symbol and order.status in {
                OrderStatus.PENDING,
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIAL,
            }:
                result.append(order)

        result.sort(key=lambda x: x.ts, reverse=True)
        return result

    def get_open_sell_order_by_symbol(self, symbol: str):
        open_orders = self.get_open_orders_by_symbol(symbol)
        for order in open_orders:
            if getattr(order.side, "name", "") == "SELL":
                return order
        return None