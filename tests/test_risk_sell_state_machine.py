from datetime import datetime, timedelta
from types import SimpleNamespace

from core.models import Order, OrderStatus, Side
from core.portfolio import Position
from engine import TradingEngine
from infra.sqlite_store import SQLiteStore


class Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def exception(self, *a, **k): pass


class Broker:
    def __init__(self, reject=False):
        self.orders, self.cancels, self.pending, self.reject = [], [], [], reject
    def set_real_tick_callback(self, cb): self.tick = cb
    def set_fill_callback(self, cb): self.fill = cb
    def set_msg_callback(self, cb): self.msg = cb
    def place_order(self, signal):
        order = Order("o%d" % (len(self.orders) + 1), signal.symbol, signal.side, signal.qty, 0,
                      signal.order_type, OrderStatus.REJECTED if self.reject else OrderStatus.SUBMITTED,
                      reason=signal.reason)
        self.orders.append(order)
        if not self.reject:
            self.pending = [{"symbol": signal.symbol, "order_no": "KR_BROKER_%d" % len(self.orders),
                             "side": "SELL", "order_qty": signal.qty, "filled_qty": 0,
                             "unfilled_qty": signal.qty, "order_price": 0, "order_status": "SUBMITTED"}]
        return order
    def cancel_order(self, **kwargs):
        self.cancels.append(kwargs)
        return 0
    def get_pending_orders(self, password=""): return list(self.pending)


def make_engine(tmp_path, broker, monkeypatch):
    monkeypatch.setattr("config_live.PAPER_TRADING", False)
    engine = TradingEngine(broker, object(), Log(), sqlite_store=SQLiteStore(tmp_path / "risk.sqlite3"), initial_cash=0)
    engine.is_running = True
    engine.portfolio.positions["A"] = Position("A", 100, 10000)
    engine._strategy_name_for_symbol = lambda symbol: "test"
    engine._strategy_cfg_float = lambda *args: -0.015
    return engine


def test_rejected_stop_is_terminal_and_not_retried(tmp_path, monkeypatch):
    broker = Broker(reject=True)
    engine = make_engine(tmp_path, broker, monkeypatch)
    engine.on_real_tick({"symbol": "A", "price": 9850, "volume": 1})
    event = engine.sqlite_store.get_open_risk_events(include_manual=True)[0]
    assert event["state"] == "MANUAL_INTERVENTION_REQUIRED"
    engine.on_real_tick({"symbol": "A", "price": 9800, "volume": 1})
    assert len(broker.orders) == 1


def test_cancel_request_waits_for_broker_disappearance(tmp_path, monkeypatch):
    broker = Broker()
    engine = make_engine(tmp_path, broker, monkeypatch)
    engine.on_real_tick({"symbol": "A", "price": 9850, "volume": 1})
    order = broker.orders[0]
    order.ts = datetime.now() - timedelta(seconds=engine.risk_sell_timeout_sec + 1)
    engine.manage_pending_orders()
    assert len(broker.cancels) == 1
    assert engine.sqlite_store.get_open_risk_events()[0]["state"] == "CANCEL_REQUESTED"
    engine.manage_pending_orders()
    assert len(broker.orders) == 1
    broker.pending = []
    engine.sync_pending_orders()
    assert engine.sqlite_store.get_open_risk_events()[0]["state"] == "CANCEL_REQUESTED"
    engine.risk_retry_delay_sec = 0
    engine.manage_pending_orders()
    assert len(broker.orders) == 1


def test_cancel_confirmation_timeout_fails_closed(tmp_path, monkeypatch):
    broker = Broker()
    engine = make_engine(tmp_path, broker, monkeypatch)
    engine.on_real_tick({"symbol": "A", "price": 9850, "volume": 1})
    order = broker.orders[0]
    order.ts = datetime.now() - timedelta(seconds=engine.risk_sell_timeout_sec + 1)
    engine.manage_pending_orders()
    event = engine.sqlite_store.get_open_risk_events(include_manual=True)[0]
    old = (datetime.now() - timedelta(seconds=engine.risk_cancel_confirm_timeout_sec + 1)).strftime("%Y-%m-%d %H:%M:%S")
    engine.sqlite_store.update_risk_event(event["event_id"], cancel_requested_at=old, last_action_at=old)
    broker.pending = []
    engine._reconcile_risk_event("A", force=True)
    assert engine.sqlite_store.get_risk_event(event["event_id"])["state"] == "MANUAL_INTERVENTION_REQUIRED"
    assert len(broker.orders) == 1


def test_pending_risk_order_is_reconciled_without_resubmit(tmp_path, monkeypatch):
    broker = Broker()
    engine = make_engine(tmp_path, broker, monkeypatch)
    engine.on_real_tick({"symbol": "A", "price": 9850, "volume": 1})
    order = broker.orders[0]
    broker.pending = [{"symbol": "A", "order_no": "KR_BROKER_1", "side": "SELL",
                       "order_qty": 100, "filled_qty": 40, "unfilled_qty": 60,
                       "order_price": 0, "order_status": "PARTIAL"}]
    engine.sync_pending_orders()
    assert len(broker.orders) == 1
    assert engine.sqlite_store.get_open_risk_events()[0]["state"] == "SELL_SUBMITTING"


def test_cumulative_fill_is_applied_once_and_closes_risk_event(tmp_path, monkeypatch):
    broker = Broker()
    engine = make_engine(tmp_path, broker, monkeypatch)
    engine.on_real_tick({"symbol": "A", "price": 9850, "volume": 1})
    broker_id = "KR_BROKER_1"

    partial = SimpleNamespace(order_id=broker_id, symbol="A", side=Side.SELL,
                              fill_qty=40, fill_price=9800, unfilled_qty=60)
    engine.on_fill(partial)
    engine.on_fill(SimpleNamespace(order_id=broker_id, symbol="A", side=Side.SELL,
                                   fill_qty=40, fill_price=9800, unfilled_qty=60))
    order = broker.orders[0]
    assert order.filled_qty == 40
    assert engine.portfolio.get_position("A").qty == 60
    assert engine.sqlite_store.get_open_risk_events()[0]["state"] == "SELL_PARTIAL"

    engine.on_fill(SimpleNamespace(order_id=broker_id, symbol="A", side=Side.SELL,
                                   fill_qty=60, fill_price=9800, unfilled_qty=0))
    assert engine.portfolio.get_position("A").qty == 0
    assert engine.sqlite_store.get_risk_event("risk-A:A:stop")["state"] == "CLOSED"
    assert len(broker.orders) == 1


def test_unmapped_fill_does_not_change_portfolio(tmp_path, monkeypatch):
    broker = Broker()
    engine = make_engine(tmp_path, broker, monkeypatch)
    before = engine.portfolio.get_position("A").qty
    engine.on_fill(SimpleNamespace(order_id="UNKNOWN", symbol="A", side=Side.SELL,
                                   fill_qty=100, fill_price=9000, unfilled_qty=0))
    assert engine.portfolio.get_position("A").qty == before
    assert len(broker.orders) == 0


def test_shutdown_gate_blocks_risk_auto_retry_and_cancel_actions(tmp_path, monkeypatch):
    broker = Broker()
    engine = make_engine(tmp_path, broker, monkeypatch)
    engine.request_shutdown()

    engine._submit_auto_sell("A", 100, "take_profit")
    engine._submit_risk_sell("A", 100, "stop", "missing-event", "A:stop")
    engine._retry_sell_after_cancel("A")
    engine.manage_pending_orders()

    assert len(broker.orders) == 0
    assert len(broker.cancels) == 0
