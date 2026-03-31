# core/fill_processor.py
from typing import Optional


class FillProcessor:
    def __init__(self, order_registry, position_manager, logger=None, telegram=None):
        self.order_registry = order_registry
        self.position_manager = position_manager
        self.logger = logger
        self.telegram = telegram

    def process_fill(self, order_no: str, code: str, side: str, fill_qty: int, fill_price: float):
        rec = self.order_registry.apply_fill(order_no, fill_qty, fill_price)

        if side == "BUY":
            self.position_manager.on_buy_fill(code, fill_qty, fill_price)
        elif side == "SELL":
            pnl = self.position_manager.on_sell_fill(code, fill_qty, fill_price)
            if self.logger:
                self.logger.info(
                    f"[SELL FILL] {code} qty={fill_qty} price={fill_price} pnl={pnl:.2f}"
                )

        if self.logger:
            self.logger.info(
                f"[FILL] order_no={order_no} code={code} side={side} fill_qty={fill_qty} fill_price={fill_price} "
                f"status={(rec.status if rec else 'UNKNOWN')}"
            )

        if self.telegram:
            try:
                self.telegram.send_message(
                    f"체결 | {code} | {side} | 수량:{fill_qty} | 가격:{fill_price} | "
                    f"상태:{rec.status if rec else 'UNKNOWN'}"
                )
            except Exception:
                pass

        return rec