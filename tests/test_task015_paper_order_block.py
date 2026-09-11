import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_broker_module():
    qt = ModuleType("PyQt5")
    qt_core = ModuleType("PyQt5.QtCore")
    qax = ModuleType("PyQt5.QAxContainer")
    qt_core.QObject = type("QObject", (), {})
    qt_core.QEventLoop = type("QEventLoop", (), {})
    qt_core.QTimer = type("QTimer", (), {})
    qax.QAxWidget = type("QAxWidget", (), {})
    sys.modules.setdefault("PyQt5", qt)
    sys.modules.setdefault("PyQt5.QtCore", qt_core)
    sys.modules.setdefault("PyQt5.QAxContainer", qax)

    module_path = Path(__file__).parents[1] / "broker" / "kiwoom_broker.py"
    spec = importlib.util.spec_from_file_location("_task015_kiwoom_broker", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BROKER_MODULE = _load_broker_module() if sys.version_info >= (3, 10) else None
requires_python_310 = pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="Kiwoom broker annotations require Python 3.10+",
)


class _Log:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


def _broker_with_send_trap():
    broker = BROKER_MODULE.KiwoomBroker.__new__(BROKER_MODULE.KiwoomBroker)
    broker.logger = _Log()
    broker.account_no = "test-account"
    broker.order_screen_no = "6000"
    calls = []
    broker._send_order_with_retry = lambda **kwargs: calls.append(kwargs) or 0
    return broker, calls


@pytest.mark.parametrize("paper_trading,allow_live_orders", [(True, True), (True, False), (False, False)])
@pytest.mark.parametrize("side_name", ["BUY", "SELL"])
@requires_python_310
def test_place_order_never_calls_send_order_when_live_gate_is_closed(
    monkeypatch,
    paper_trading,
    allow_live_orders,
    side_name,
):
    monkeypatch.setattr(BROKER_MODULE.config, "PAPER_TRADING", paper_trading)
    monkeypatch.setattr(BROKER_MODULE.config, "ALLOW_LIVE_ORDERS", allow_live_orders)
    broker, send_calls = _broker_with_send_trap()
    signal = BROKER_MODULE.Signal(
        symbol="005930",
        side=getattr(BROKER_MODULE.Side, side_name),
        qty=1,
        reason="TASK-015",
    )

    order = broker.place_order(signal)

    assert send_calls == []
    assert order.status == BROKER_MODULE.OrderStatus.SUBMITTED


@pytest.mark.parametrize("paper_trading,allow_live_orders", [(True, True), (True, False), (False, False)])
@requires_python_310
def test_cancel_order_never_calls_send_order_when_live_gate_is_closed(
    monkeypatch,
    paper_trading,
    allow_live_orders,
):
    monkeypatch.setattr(BROKER_MODULE.config, "PAPER_TRADING", paper_trading)
    monkeypatch.setattr(BROKER_MODULE.config, "ALLOW_LIVE_ORDERS", allow_live_orders)
    broker, send_calls = _broker_with_send_trap()

    result = broker.cancel_order("005930", "paper-order", 1)

    assert result == 0
    assert send_calls == []
