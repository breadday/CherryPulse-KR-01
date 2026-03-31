from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


@dataclass
class TickData:
    symbol: str
    price: float
    volume: int
    ts: datetime


@dataclass
class Signal:
    symbol: str
    side: Side
    qty: int
    reason: str
    price: Optional[float] = None
    order_type: OrderType = OrderType.MARKET
    ts: datetime = field(default_factory=datetime.now)


@dataclass
class Order:
    order_id: str
    symbol: str
    side: Side
    qty: int
    price: Optional[float]
    order_type: OrderType
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    reason: str = ""
    ts: datetime = field(default_factory=datetime.now)


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    fill_qty: int
    fill_price: float
    ts: datetime = field(default_factory=datetime.now)