from core.models import Order, OrderStatus, Side
from core.portfolio import Position
from engine import TradingEngine


class _Log:
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def exception(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass


class _Broker:
    def set_real_tick_callback(self, callback): self.tick_callback = callback
    def set_fill_callback(self, callback): self.fill_callback = callback
    def set_msg_callback(self, callback): self.msg_callback = callback
    def place_order(self, signal):
        self.orders = getattr(self, "orders", [])
        order = Order("risk-order", signal.symbol, signal.side, signal.qty, 0, signal.order_type, OrderStatus.SUBMITTED, reason=signal.reason)
        self.orders.append(order)
        return order


class _Strategy:
    def __init__(self): self.calls = 0
    def generate_signal(self, tick, portfolio):
        self.calls += 1
        return None


def test_risk_guard_runs_before_external_data_and_strategy():
    broker, strategy = _Broker(), _Strategy()
    engine = TradingEngine(broker, strategy, _Log(), initial_cash=0)
    engine.portfolio.positions["A"] = Position("A", 100, 10000)
    engine._strategy_name_for_symbol = lambda symbol: "test"
    engine._strategy_cfg_float = lambda *args: -0.015
    engine._build_external_scores = lambda tick: (_ for _ in ()).throw(AssertionError("late path"))

    engine.on_real_tick({"symbol": "A", "price": 9850, "volume": 1})

    assert len(broker.orders) == 1
    assert broker.orders[0].qty == 100
    assert strategy.calls == 0
