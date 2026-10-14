"""Paper-only one-share limit-buy boundary; no live host, no retry, no ledger.

Order identity (``kt10000`` 주식 매수주문, ``POST /api/dostk/ordr``) and its
request fields are confirmed against the official REST API guide and account
examples; the implementation below is independent. Submission targets the
fixed mock host only. Quantity is fixed to one share and the order type is
fixed to a limit price, following the confirmed Q12 policy. Broker order
numbers never leave the submitting process in chat-safe reports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BUY_API_ID = "kt10000"
ORDER_PATH = "/api/dostk/ordr"
MOCK_ORDER_URL = "https://mockapi.kiwoom.com" + ORDER_PATH
LIMIT_TRADE_TYPE = "0"
DEMO_QUANTITY = 1
MAX_DEMO_PRICE = 100000

_SYMBOL_PATTERN = re.compile(r"[0-9]{6}")
_PRICE_PATTERN = re.compile(r"[0-9]+(\.[0-9]+)?")


@dataclass(frozen=True, slots=True)
class BuyPreview:
    """One validated demonstration buy; market orders cannot be expressed."""

    symbol: str
    price: str

    def __post_init__(self) -> None:
        """Reject anything but a six-digit symbol and a capped limit price."""
        if _SYMBOL_PATTERN.fullmatch(self.symbol) is None:
            raise ValueError("ORDER_SYMBOL_INVALID")
        if _PRICE_PATTERN.fullmatch(self.price) is None:
            raise ValueError("ORDER_PRICE_INVALID")
        if int(self.price.split(".", 1)[0]) > MAX_DEMO_PRICE:
            raise ValueError("ORDER_PRICE_CAPPED")
        if int(self.price.split(".", 1)[0]) <= 0:
            raise ValueError("ORDER_PRICE_INVALID")


def build_buy_body(preview: BuyPreview) -> dict[str, str]:
    """Build the fixed limit-buy body; exchange and quantity are constants."""
    return {
        "dmst_stex_tp": "KRX",
        "stk_cd": preview.symbol,
        "ord_qty": str(DEMO_QUANTITY),
        "trde_tp": LIMIT_TRADE_TYPE,
        "ord_uv": preview.price,
        "cond_uv": "",
    }


def classify_order_response(payload: object) -> tuple[bool, str]:
    """Decide acknowledgement without retaining broker identifiers."""
    if not isinstance(payload, dict):
        return False, "RESPONSE_INVALID"
    code = payload.get("return_code")
    if type(code) not in (int, str) or code not in (0, "0"):
        return False, "API_SUCCESS_UNCONFIRMED"
    order_number = payload.get("ord_no")
    if not isinstance(order_number, str) or not order_number.strip():
        return False, "ORDER_NUMBER_MISSING"
    return True, "ORDER_ACKED"
