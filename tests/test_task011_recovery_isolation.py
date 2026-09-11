import sys
from types import ModuleType, SimpleNamespace

import pytest


def _install_qt_stubs():
    qt = ModuleType("PyQt5")
    qt_core = ModuleType("PyQt5.QtCore")
    qt_widgets = ModuleType("PyQt5.QtWidgets")
    qax = ModuleType("PyQt5.QAxContainer")

    class QObject:
        pass

    class QEventLoop:
        pass

    class QTimer:
        pass

    class QApplication:
        pass

    class QAxWidget:
        pass

    qt_core.QObject = QObject
    qt_core.QEventLoop = QEventLoop
    qt_core.QTimer = QTimer
    qt_widgets.QApplication = QApplication
    qax.QAxWidget = QAxWidget
    broker_module = ModuleType("broker.kiwoom_broker")
    broker_module.KiwoomBroker = type("KiwoomBroker", (), {})
    telegram_module = ModuleType("infra.telegram_notifier")
    telegram_module.TelegramNotifier = type("TelegramNotifier", (), {})
    sys.modules.setdefault("PyQt5", qt)
    sys.modules.setdefault("PyQt5.QtCore", qt_core)
    sys.modules.setdefault("PyQt5.QtWidgets", qt_widgets)
    sys.modules.setdefault("PyQt5.QAxContainer", qax)
    sys.modules.setdefault("broker.kiwoom_broker", broker_module)
    sys.modules.setdefault("infra.telegram_notifier", telegram_module)


_install_qt_stubs()

import main_live
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


class _PendingQueryError(RuntimeError):
    pass


class _RecoveryBroker:
    def __init__(self):
        self.connect_calls = 0

    def remove_real(self, _screen):
        pass

    def connect(self):
        self.connect_calls += 1


class _RecoveryEngine:
    def __init__(self, calls):
        self.calls = calls

    def sync_account(self, password=""):
        self.calls.append(("sync_account", password))

    def sync_pending_orders(self, password=""):
        self.calls.append(("sync_pending_orders", password))

    def health_check(self):
        self.calls.append(("health_check", ""))


def _recovery_app(monkeypatch, now_hhmm):
    calls = []
    app = main_live.MainLiveApp.__new__(main_live.MainLiveApp)
    app.shutting_down = False
    app.reconnect_in_progress = False
    app.reconnect_blocked_until_ts = 0.0
    app.last_reconnect_attempt_ts = 0.0
    app.reconnect_attempt_count_by_reason = {}
    app.condition_started = False
    app.condition_failure_count = 0
    app.last_real_tick_received_ts = 0.0
    app.logger = _Log()
    app.broker = _RecoveryBroker()
    app.engine = _RecoveryEngine(calls)
    app._now_hhmm = lambda: now_hhmm
    app._in_kiwoom_restart_window = lambda: False
    app._market_phase = lambda: "pre_open_wait"
    app._send_telegram_throttled = lambda *args, **kwargs: None
    app.load_snapshot_and_subscribe = lambda: calls.append(("load_snapshot", ""))
    app._refresh_real_registration = lambda: calls.append(("refresh_registration", ""))
    app.start_condition_search = lambda: calls.append(("condition_search", ""))
    monkeypatch.setattr(main_live.time, "sleep", lambda _seconds: None)
    return app, calls


@pytest.mark.parametrize("now_hhmm", ["14:39", "14:40", "14:41", "15:19", "15:20", "15:21", "15:34"])
def test_recovery_remains_available_before_shutdown_boundary(monkeypatch, now_hhmm):
    app, _calls = _recovery_app(monkeypatch, now_hhmm)

    app._recover_broker_session("broker_disconnected")

    assert app.broker.connect_calls == 1


@pytest.mark.parametrize("now_hhmm", ["15:35", "15:36"])
def test_recovery_is_blocked_at_shutdown_boundary(monkeypatch, now_hhmm):
    app, _calls = _recovery_app(monkeypatch, now_hhmm)

    app._recover_broker_session("broker_disconnected")

    assert app.broker.connect_calls == 0


def test_heartbeat_runs_shutdown_gate_before_risk_observation():
    calls = []
    app = main_live.MainLiveApp.__new__(main_live.MainLiveApp)
    app.shutting_down = False
    app.booting = True
    app.auto_shutdown = lambda: calls.append("auto_shutdown")
    app.engine = SimpleNamespace(
        observe_risk_events=lambda reason="": calls.append(("observe", reason)),
        manage_pending_orders=lambda: calls.append("manage_pending"),
    )

    app.on_heartbeat()

    assert calls == ["auto_shutdown", ("observe", "heartbeat"), "manage_pending"]


def test_shutdown_sets_engine_gate_before_reconciliation(monkeypatch):
    calls = []

    class ShutdownEngine:
        def __init__(self):
            self.shutdown_requested = False

        def request_shutdown(self):
            self.shutdown_requested = True
            calls.append("gate")

        def observe_risk_events(self, reason=""):
            calls.append(("observe", self.shutdown_requested, reason))

        def sync_pending_orders(self, password=""):
            calls.append(("pending", self.shutdown_requested, password))

        def sync_account(self, password=""):
            calls.append(("account", self.shutdown_requested, password))

        def stop(self):
            calls.append("stop")

    app = main_live.MainLiveApp.__new__(main_live.MainLiveApp)
    app.shutting_down = False
    app.logger = _Log()
    app.engine = ShutdownEngine()
    app.broker = SimpleNamespace(
        stop_condition=lambda _name: calls.append("stop_condition"),
        remove_real=lambda _screen: calls.append("remove_real"),
    )
    app._log_open_positions_before_shutdown = lambda: calls.append("log_positions")
    monkeypatch.setattr(main_live.config, "DRY_RUN", False)
    monkeypatch.setattr(main_live.os, "_exit", lambda _code: calls.append("exit"))
    monkeypatch.setattr(app, "_market_phase", lambda: "market_session")

    app.shutdown()

    assert calls[:5] == [
        "gate",
        "log_positions",
        ("observe", True, "shutdown"),
        ("pending", True, main_live.ACCOUNT_PASSWORD),
        ("account", True, main_live.ACCOUNT_PASSWORD),
    ]


def test_repeated_heartbeat_after_shutdown_starts_no_engine_work():
    calls = []
    app = main_live.MainLiveApp.__new__(main_live.MainLiveApp)
    app.shutting_down = True
    app.auto_shutdown = lambda: calls.append("auto_shutdown")
    app.engine = SimpleNamespace(
        observe_risk_events=lambda reason="": calls.append(("observe", reason)),
        manage_pending_orders=lambda: calls.append("manage_pending"),
    )

    for _attempt in range(3):
        app.on_heartbeat()

    assert calls == ["auto_shutdown", "auto_shutdown", "auto_shutdown"]


def test_pending_query_failure_does_not_manualize_unrelated_events(tmp_path):
    class QueryFailureBroker:
        def __init__(self):
            self.calls = 0

        def get_pending_orders(self, password=""):
            self.calls += 1
            if self.calls == 1:
                return []
            raise _PendingQueryError("pending unavailable")

        def set_real_tick_callback(self, _callback):
            pass

        def set_fill_callback(self, _callback):
            pass

        def set_msg_callback(self, _callback):
            pass

    store = SQLiteStore(tmp_path / "risk.sqlite3")
    for event_id, symbol in (("risk-A", "A"), ("risk-B", "B")):
        store.create_risk_event(
            event_id=event_id,
            idempotency_key=event_id,
            symbol=symbol,
            position_key="position",
            qty=10,
            state="SELL_SUBMITTING",
        )

    engine = TradingEngine(QueryFailureBroker(), object(), _Log(), sqlite_store=store, initial_cash=0)
    engine.portfolio.positions["A"] = Position("A", 10, 100)
    engine.portfolio.positions["B"] = Position("B", 10, 100)

    engine.sync_pending_orders()

    assert store.get_risk_event("risk-A")["state"] == "SELL_SUBMITTING"
    assert store.get_risk_event("risk-B")["state"] == "SELL_SUBMITTING"
