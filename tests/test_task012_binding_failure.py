import pytest

from core.models import Order, OrderStatus, OrderType, Side
from core.portfolio import Position
from engine import TradingEngine
from infra.sqlite_store import SQLiteStore


class _Log:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class _SubmitBroker:
    def __init__(self, pending):
        self.pending = pending
        self.place_calls = 0
        self.cancel_calls = 0

    def set_real_tick_callback(self, _callback):
        pass

    def set_fill_callback(self, _callback):
        pass

    def set_msg_callback(self, _callback):
        pass

    def place_order(self, signal):
        self.place_calls += 1
        return Order(
            order_id=f"LOCAL-{self.place_calls}",
            symbol=signal.symbol,
            side=signal.side,
            qty=signal.qty,
            price=0,
            order_type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            reason=signal.reason,
        )

    def get_pending_orders(self, password=""):
        return list(self.pending)

    def cancel_order(self, **kwargs):
        self.cancel_calls += 1
        return 0


def _risk_event(store):
    store.create_risk_event(
        event_id="risk-A",
        idempotency_key="A:stop",
        symbol="A",
        position_key="position",
        qty=100,
        state="STOP_DETECTED",
    )


def _engine(tmp_path, broker):
    store = SQLiteStore(tmp_path / "risk.sqlite3")
    _risk_event(store)
    engine = TradingEngine(broker, object(), _Log(), sqlite_store=store, initial_cash=0)
    engine.portfolio.positions["A"] = Position("A", 100, 100)
    return engine, store


@pytest.mark.parametrize("pending", [[], [
    {"symbol": "A", "order_no": "BROKER-1", "side": "SELL", "order_qty": 100,
     "filled_qty": 0, "unfilled_qty": 100},
    {"symbol": "A", "order_no": "BROKER-2", "side": "SELL", "order_qty": 100,
     "filled_qty": 0, "unfilled_qty": 100},
]])
def test_missing_or_ambiguous_broker_identity_fails_closed(tmp_path, pending):
    broker = _SubmitBroker(pending)
    engine, store = _engine(tmp_path, broker)

    engine._submit_risk_sell("A", 100, "stop", "risk-A", "A:stop")

    assert broker.place_calls == 1
    assert broker.cancel_calls == 0
    assert engine.order_manager.orders == {}
    assert engine.order_manager.local_to_broker_id == {}
    assert engine.order_manager.broker_to_local_id == {}
    assert engine.risk_order_events == {}
    assert engine.sell_in_progress == set()
    event = store.get_risk_event("risk-A")
    assert event["state"] == "MANUAL_INTERVENTION_REQUIRED"
    assert event["local_order_id"] == ""
    assert event["broker_order_id"] == ""


def test_broker_identity_conflict_restores_pre_submit_state(tmp_path):
    pending = [{
        "symbol": "A", "order_no": "BROKER-1", "side": "SELL", "order_qty": 100,
        "filled_qty": 0, "unfilled_qty": 100,
    }]
    broker = _SubmitBroker(pending)
    engine, store = _engine(tmp_path, broker)
    existing = Order(
        "EXISTING", "B", Side.SELL, 10, 0, OrderType.MARKET,
        OrderStatus.SUBMITTED, purpose="RISK_STOP", risk_event_id="risk-B",
    )
    engine.order_manager.register(existing)
    assert engine.order_manager.bind_broker_order_id("EXISTING", "BROKER-1", "risk-B") is existing
    before_orders = dict(engine.order_manager.orders)
    before_local = dict(engine.order_manager.local_to_broker_id)
    before_broker = dict(engine.order_manager.broker_to_local_id)

    engine._submit_risk_sell("A", 100, "stop", "risk-A", "A:stop")

    assert broker.place_calls == 1
    assert broker.cancel_calls == 0
    assert engine.order_manager.orders == before_orders
    assert engine.order_manager.local_to_broker_id == before_local
    assert engine.order_manager.broker_to_local_id == before_broker
    assert engine.risk_order_events == {}
    assert engine.sell_in_progress == set()
    assert store.get_risk_event("risk-A")["state"] == "MANUAL_INTERVENTION_REQUIRED"
