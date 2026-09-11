from types import SimpleNamespace

from core.models import Order, OrderStatus, OrderType, Side, Signal
from core.portfolio import Position
from engine import TradingEngine


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
        self.orders = []

    def set_real_tick_callback(self, callback):
        self.tick_callback = callback

    def set_fill_callback(self, callback):
        self.fill_callback = callback

    def set_msg_callback(self, callback):
        self.msg_callback = callback

    def place_order(self, signal):
        order = Order(
            order_id=f"order-{len(self.orders) + 1}",
            symbol=signal.symbol,
            side=signal.side,
            qty=signal.qty,
            price=signal.price,
            order_type=signal.order_type,
            status=OrderStatus.SUBMITTED,
            reason=signal.reason,
        )
        self.orders.append(order)
        return order

    def get_pending_orders(self, password=""):
        if not self.orders:
            return []
        order = self.orders[-1]
        return [
            {
                "symbol": order.symbol,
                "side": "SELL",
                "order_no": f"broker-{len(self.orders)}",
                "order_qty": order.qty,
                "filled_qty": 0,
                "unfilled_qty": order.qty,
                "order_price": 0,
                "order_status": "SUBMITTED",
            }
        ]


class _NoEntryStrategy:
    def __init__(self):
        self.calls = 0

    def generate_signal(self, tick, portfolio):
        self.calls += 1
        return None


def _engine(initial_cash=1_000_000):
    broker = _Broker()
    strategy = _NoEntryStrategy()
    engine = TradingEngine(broker, strategy, _Log(), initial_cash=initial_cash)
    engine.is_running = True
    return engine, broker, strategy


def _buy_signal(strategy_name):
    signal = Signal(
        symbol="BUY",
        side=Side.BUY,
        qty=1,
        price=100,
        order_type=OrderType.LIMIT,
        reason="TASK-018",
    )
    signal.strategy_name = strategy_name
    return signal


def test_daily_loss_uses_current_day_baseline(monkeypatch):
    engine, _broker, _strategy = _engine()
    monkeypatch.setattr("config_live.MAX_DAILY_LOSS", -100.0)
    engine.portfolio.realized_pnl = -150.0

    engine.daily_realized_pnl_base = -40.0
    assert engine._daily_loss_limit_reached() == (True, -110.0, -100.0)

    engine.daily_realized_pnl_base = -60.0
    assert engine._daily_loss_limit_reached() == (False, -90.0, -100.0)


def test_daily_loss_blocks_new_buy(monkeypatch):
    engine, _broker, _strategy = _engine()
    monkeypatch.setattr(engine, "reset_daily_counters_if_needed", lambda: None)
    monkeypatch.setattr(engine, "is_market_open", lambda: True)
    monkeypatch.setattr(engine, "_daily_loss_limit_reached", lambda: (True, -300_000.0, -300_000.0))

    allowed, reason = engine.can_send_order(
        _buy_signal("bottom_reversal"),
        SimpleNamespace(price=100, price_change_pct=0.0, volume=100),
    )

    assert allowed is False
    assert reason == "daily loss limit reached (-300000<=-300000)"


def test_strategy_consecutive_loss_protects_only_that_strategy(monkeypatch):
    engine, _broker, _strategy = _engine()
    engine.consecutive_loss_count_by_strategy["bottom_reversal"] = 2
    monkeypatch.setattr(engine, "_strategy_max_consecutive_loss", lambda _name: 2)
    monkeypatch.setattr(engine, "_daily_loss_limit_reached", lambda: (False, 0.0, -300_000.0))

    engine._check_engine_protection(strategy_name="bottom_reversal")

    assert engine.engine_protected is False
    assert engine._is_strategy_protected("bottom_reversal") is True
    assert engine._is_strategy_protected("leader_pullback") is False


def test_protected_engine_still_submits_independent_stop_order(monkeypatch):
    engine, broker, strategy = _engine(initial_cash=0)
    engine.engine_protected = True
    engine.portfolio.positions["RISK"] = Position("RISK", 10, 100)
    engine._strategy_name_for_symbol = lambda _symbol: "bottom_reversal"
    engine._strategy_cfg_float = lambda *_args: -0.02
    engine._build_external_scores = lambda _tick: (_ for _ in ()).throw(
        AssertionError("entry data path must not run before risk stop")
    )

    engine.on_real_tick({"symbol": "RISK", "price": 98, "volume": 1})

    assert len(broker.orders) == 1
    assert broker.orders[0].side == Side.SELL
    assert broker.orders[0].qty == 10
    assert broker.orders[0].purpose == "RISK_STOP"
    assert strategy.calls == 0
