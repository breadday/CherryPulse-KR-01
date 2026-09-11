from types import SimpleNamespace

import pytest

from core.models import Order, OrderStatus, OrderType, Side
from core.portfolio import Position
from engine import TradingEngine
from infra.sqlite_store import SQLiteStore


class _AccountQueryError(RuntimeError):
    pass


class _Log:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class _Broker:
    def __init__(self):
        self.place_calls = 0
        self.cancel_calls = 0

    def set_real_tick_callback(self, _callback):
        pass

    def set_fill_callback(self, _callback):
        pass

    def set_msg_callback(self, _callback):
        pass

    def get_deposit(self, password=""):
        raise _AccountQueryError("account unavailable")


def _engine_with_two_events(tmp_path):
    store = SQLiteStore(tmp_path / "risk.sqlite3")
    broker = _Broker()
    engine = TradingEngine(broker, object(), _Log(), sqlite_store=store, initial_cash=0)
    for symbol in ("A", "B"):
        event_id = f"risk-{symbol}"
        local_id = f"LOCAL-{symbol}"
        broker_id = f"BROKER-{symbol}"
        store.create_risk_event(
            event_id=event_id,
            idempotency_key=f"{symbol}:stop",
            symbol=symbol,
            position_key="position",
            qty=100,
            state="SELL_SUBMITTING",
        )
        store.update_risk_event(
            event_id,
            local_order_id=local_id,
            broker_order_id=broker_id,
        )
        engine.portfolio.positions[symbol] = Position(symbol, 100, 100)
        order = Order(
            local_id,
            symbol,
            Side.SELL,
            100,
            0,
            OrderType.MARKET,
            OrderStatus.SUBMITTED,
            purpose="RISK_STOP",
            risk_event_id=event_id,
        )
        engine.order_manager.register(order)
        assert engine.order_manager.bind_broker_order_id(local_id, broker_id, event_id) is order
        engine.risk_order_events[local_id] = event_id
    return engine, store, broker


def test_cumulative_fill_is_isolated_between_risk_events(tmp_path):
    engine, store, _broker = _engine_with_two_events(tmp_path)

    engine.on_fill(SimpleNamespace(
        order_id="BROKER-A", symbol="A", side=Side.SELL,
        fill_qty=40, fill_price=98, unfilled_qty=60,
    ))
    engine.on_fill(SimpleNamespace(
        order_id="BROKER-A", symbol="A", side=Side.SELL,
        fill_qty=40, fill_price=98, unfilled_qty=60,
    ))
    engine.on_fill(SimpleNamespace(
        order_id="BROKER-A", symbol="A", side=Side.SELL,
        fill_qty=60, fill_price=97, unfilled_qty=0,
    ))

    assert engine.portfolio.get_position("A").qty == 0
    assert engine.order_manager.get_order("LOCAL-A").filled_qty == 100
    assert store.get_risk_event("risk-A")["state"] == "CLOSED"
    assert engine.portfolio.get_position("B").qty == 100
    assert engine.order_manager.get_order("LOCAL-B").filled_qty == 0
    assert store.get_risk_event("risk-B")["state"] == "SELL_SUBMITTING"


def test_account_query_failure_preserves_all_risk_events(tmp_path):
    engine, store, broker = _engine_with_two_events(tmp_path)
    before_a = dict(store.get_risk_event("risk-A"))
    before_b = dict(store.get_risk_event("risk-B"))

    with pytest.raises(_AccountQueryError):
        engine.sync_account()

    assert store.get_risk_event("risk-A") == before_a
    assert store.get_risk_event("risk-B") == before_b
    assert broker.place_calls == 0
    assert broker.cancel_calls == 0
