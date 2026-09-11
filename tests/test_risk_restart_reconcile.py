from datetime import datetime

from core.models import Order, OrderStatus, OrderType, Side
from core.order_manager import OrderManager
from core.portfolio import Position
from engine import TradingEngine
from infra.sqlite_store import SQLiteStore


def risk_order(local="ORD_LOCAL_1", event="risk-1"):
    return Order(local, "A", Side.SELL, 100, 0, OrderType.MARKET,
                 OrderStatus.SUBMITTED, purpose="RISK_STOP",
                 risk_event_id=event)


def test_order_identity_binding_is_explicit_and_fail_closed():
    manager = OrderManager()
    order = risk_order()
    manager.register(order)

    assert manager.bind_broker_order_id("ORD_LOCAL_1", "KR_BROKER_77", "risk-1") is order
    assert manager.get_order_by_broker_id("KR_BROKER_77") is order
    assert manager.local_to_broker_id == {"ORD_LOCAL_1": "KR_BROKER_77"}

    before = (dict(manager.local_to_broker_id), dict(manager.broker_to_local_id), order.broker_order_id)
    assert manager.bind_broker_order_id("ORD_LOCAL_1", "ORD_LOCAL_1", "risk-1") is None
    assert manager.bind_broker_order_id("unknown", "KR_BROKER_88", "risk-1") is None
    assert manager.bind_broker_order_id("ORD_LOCAL_1", "KR_BROKER_88", "risk-2") is None
    assert (manager.local_to_broker_id, manager.broker_to_local_id, order.broker_order_id) == before


def test_risk_event_query_rejects_zero_and_duplicate_open_orders():
    manager = OrderManager()
    assert manager.get_open_risk_sell_order_by_event("risk-1") is None
    first = risk_order()
    manager.register(first)
    assert manager.get_open_risk_sell_order_by_event("risk-1") is first
    manager.register(risk_order("ORD_LOCAL_2"))
    assert manager.get_open_risk_sell_order_by_event("risk-1") is None


def test_unmapped_fill_cannot_mutate_order_manager():
    manager = OrderManager()
    order = risk_order()
    manager.register(order)
    assert manager.get_order_by_broker_id("KR_BROKER_77") is None
    assert order.filled_qty == 0


class _PendingBroker:
    def __init__(self):
        self.place_calls = 0
        self.cancel_calls = 0
        self.pending = [{
            "symbol": "A", "order_no": "BROKER_STOP_1", "side": "SELL",
            "order_qty": 100, "filled_qty": 40, "unfilled_qty": 60,
            "order_price": 0, "order_status": "PARTIAL",
        }]

    def set_real_tick_callback(self, callback): pass
    def set_fill_callback(self, callback): pass
    def set_msg_callback(self, callback): pass
    def get_pending_orders(self, password=""): return list(self.pending)
    def place_order(self, signal):
        self.place_calls += 1
        raise AssertionError("pending reconciliation must not place an order")
    def cancel_order(self, **kwargs):
        self.cancel_calls += 1
        raise AssertionError("binding failure must not cancel an order")


class _Log:
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def exception(self, *args, **kwargs): pass


def test_pending_binding_failure_rolls_back_local_state_and_mapping(tmp_path, monkeypatch):
    broker = _PendingBroker()
    store = SQLiteStore(tmp_path / "risk.sqlite3")
    store.create_risk_event(
        event_id="risk-A:position:stop", idempotency_key="A:position:stop",
        symbol="A", position_key="position", qty=100,
        state="SELL_SUBMITTING",
    )
    store.update_risk_event(
        "risk-A:position:stop", local_order_id="LOCAL_STOP_1",
        broker_order_id="BROKER_STOP_1",
    )
    engine = TradingEngine(broker, object(), _Log(), sqlite_store=store, initial_cash=0)
    engine.portfolio.positions["A"] = Position("A", 100, 100)
    before_orders = dict(engine.order_manager.orders)
    before_local = dict(engine.order_manager.local_to_broker_id)
    before_broker = dict(engine.order_manager.broker_to_local_id)
    before_events = dict(engine.risk_order_events)

    def mutating_failure(local_id, broker_id, event_id=""):
        order = engine.order_manager.orders[local_id]
        order.broker_order_id = broker_id
        engine.order_manager.local_to_broker_id[local_id] = broker_id
        engine.order_manager.broker_to_local_id[broker_id] = local_id
        return None

    monkeypatch.setattr(engine.order_manager, "bind_broker_order_id", mutating_failure)
    engine.sync_pending_orders()

    assert engine.order_manager.orders == before_orders
    assert engine.order_manager.local_to_broker_id == before_local
    assert engine.order_manager.broker_to_local_id == before_broker
    assert engine.risk_order_events == before_events
    assert store.get_risk_event("risk-A:position:stop")["state"] == "MANUAL_INTERVENTION_REQUIRED"
    assert broker.place_calls == 0
    assert broker.cancel_calls == 0


def test_manual_intervention_is_scoped_to_identified_event(tmp_path):
    store = SQLiteStore(tmp_path / "risk.sqlite3")
    for event_id, symbol in (("risk-A", "A"), ("risk-B", "B")):
        store.create_risk_event(
            event_id=event_id, idempotency_key=event_id, symbol=symbol,
            position_key="position", qty=10, state="SELL_SUBMITTING",
        )
    engine = TradingEngine(_PendingBroker(), object(), _Log(), sqlite_store=store, initial_cash=0)

    engine._mark_open_risk_manual("identity failure", event_id="risk-A")

    assert store.get_risk_event("risk-A")["state"] == "MANUAL_INTERVENTION_REQUIRED"
    assert store.get_risk_event("risk-B")["state"] == "SELL_SUBMITTING"
