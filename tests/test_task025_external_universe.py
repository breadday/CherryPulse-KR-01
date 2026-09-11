from datetime import datetime, timezone
from types import SimpleNamespace
from types import ModuleType
import json
import sys

import pytest

import config_live

try:
    import PyQt5  # noqa: F401
except ImportError:
    pyqt = ModuleType("PyQt5")
    qt_core = ModuleType("PyQt5.QtCore")
    qt_widgets = ModuleType("PyQt5.QtWidgets")
    qax_container = ModuleType("PyQt5.QAxContainer")

    class QtPlaceholder:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def singleShot(*_args):
            pass

    qt_core.QObject = QtPlaceholder
    qt_core.QEventLoop = QtPlaceholder
    qt_core.QTimer = QtPlaceholder
    qt_widgets.QApplication = QtPlaceholder
    qax_container.QAxWidget = QtPlaceholder
    sys.modules.update(
        {
            "PyQt5": pyqt,
            "PyQt5.QtCore": qt_core,
            "PyQt5.QtWidgets": qt_widgets,
            "PyQt5.QAxContainer": qax_container,
        }
    )

fake_broker_module = ModuleType("broker.kiwoom_broker")
fake_broker_module.KiwoomBroker = type("KiwoomBroker", (), {})
sys.modules["broker.kiwoom_broker"] = fake_broker_module
fake_telegram_module = ModuleType("infra.telegram_notifier")
fake_telegram_module.TelegramNotifier = type("TelegramNotifier", (), {})
sys.modules["infra.telegram_notifier"] = fake_telegram_module

import main_live
from selectors.external_candidate_provider import ExternalCandidateError
from universe_manager import UniverseManager


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))

    def exception(self, message):
        self.messages.append(("exception", message))


class FakeUniverse:
    strategy_names = ["bottom_reversal", "leader_pullback"]
    external_candidate_path = None

    def __init__(self, candidates=None, error=None):
        self.candidates = candidates or []
        self.error = error
        self.calls = []

    def load_external_candidates(self, as_of=None):
        self.calls.append(("load", as_of))
        if self.error:
            raise self.error
        return self.candidates

    def external_codes(self):
        return [candidate.symbol for candidate in self.candidates]

    def strategy_source_codes(self, strategy, source):
        return [candidate.symbol for candidate in self.candidates if candidate.strategy_tag == strategy]


def _app(monkeypatch, enabled, universe):
    app = object.__new__(main_live.MainLiveApp)
    app.universe = universe
    app.logger = FakeLogger()
    app.telegram_alert_last_sent_ts = {}
    app.telegram = None
    monkeypatch.setattr(main_live.config, "ENABLE_EXTERNAL_UNIVERSE", enabled, raising=False)
    app._refresh_real_registration = lambda: app.universe.calls.append(("refresh",))
    app._store_strategy_universe_snapshot = lambda: app.universe.calls.append(("store",))
    app._log_strategy_universe_summary = lambda prefix: app.universe.calls.append(("summary", prefix))
    app._send_telegram_throttled = lambda *args, **kwargs: app.universe.calls.append(("alert", args[0]))
    return app


def test_disabled_does_not_read_or_refresh(monkeypatch):
    universe = FakeUniverse()
    app = _app(monkeypatch, False, universe)

    assert app.load_external_candidates_and_subscribe() == []
    assert universe.calls == []


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "off", "enabled"])
def test_config_external_universe_is_fail_closed(monkeypatch, value):
    monkeypatch.delenv("ENABLE_EXTERNAL_UNIVERSE", raising=False)
    if value is not None:
        monkeypatch.setenv("ENABLE_EXTERNAL_UNIVERSE", value)

    import importlib

    loaded = importlib.reload(config_live)
    try:
        assert loaded.ENABLE_EXTERNAL_UNIVERSE is False
        assert loaded.EXTERNAL_CANDIDATE_FILE == "external_candidates.json"
    finally:
        monkeypatch.delenv("ENABLE_EXTERNAL_UNIVERSE", raising=False)
        importlib.reload(config_live)


def test_config_external_universe_accepts_only_explicit_true_values(monkeypatch):
    import importlib

    try:
        for value in ("1", "true", "TRUE", " yes ", "on"):
            monkeypatch.setenv("ENABLE_EXTERNAL_UNIVERSE", value)
            assert importlib.reload(config_live).ENABLE_EXTERNAL_UNIVERSE is True
    finally:
        monkeypatch.delenv("ENABLE_EXTERNAL_UNIVERSE", raising=False)
        importlib.reload(config_live)


def test_summary_reports_external_counts(monkeypatch):
    universe = FakeUniverse(
        [SimpleNamespace(symbol="005930", strategy_tag="bottom_reversal")]
    )
    app = _app(monkeypatch, True, universe)
    universe.strategy_counts = lambda: {"bottom_reversal": 1}
    universe.snapshot_codes = lambda: []
    universe.condition_codes = lambda: []
    main_live.MainLiveApp._log_strategy_universe_summary(app, "test")

    message = next(message for level, message in app.logger.messages if level == "info")
    assert "external_count=1" in message
    assert "'bottom_reversal': 1" in message


def test_opt_in_uses_timezone_aware_time_and_refreshes(monkeypatch):
    candidate = SimpleNamespace(symbol="005930", strategy_tag="bottom_reversal")
    universe = FakeUniverse([candidate])
    app = _app(monkeypatch, True, universe)

    assert app.load_external_candidates_and_subscribe() == [candidate]
    assert universe.calls[0][0] == "load"
    assert universe.calls[0][1].tzinfo == timezone.utc
    assert [call[0] for call in universe.calls] == ["load", "refresh", "store", "summary"]


@pytest.mark.parametrize("error", [ExternalCandidateError("invalid JSON"), ExternalCandidateError("not found")])
def test_external_failure_isolated_and_throttled(monkeypatch, error):
    universe = FakeUniverse(error=error)
    app = _app(monkeypatch, True, universe)

    assert app.load_external_candidates_and_subscribe() == []
    assert [call[0] for call in universe.calls] == [
        "load",
        "refresh",
        "store",
        "summary",
        "alert",
    ]


def test_external_failure_cleanup_errors_do_not_escape(monkeypatch):
    universe = FakeUniverse(error=ExternalCandidateError("invalid schema"))
    app = _app(monkeypatch, True, universe)
    app._refresh_real_registration = lambda: (_ for _ in ()).throw(RuntimeError("register"))
    app._store_strategy_universe_snapshot = lambda: (_ for _ in ()).throw(RuntimeError("store"))
    app._log_strategy_universe_summary = lambda _prefix: (_ for _ in ()).throw(RuntimeError("summary"))

    assert app.load_external_candidates_and_subscribe() == []
    assert ("alert", "external_universe_load_failed") in universe.calls
    warnings = [message for level, message in app.logger.messages if level == "warning"]
    assert len(warnings) == 3


def test_invalid_reload_clears_prior_external_and_preserves_snapshot(monkeypatch, tmp_path):
    path = tmp_path / "external.json"
    universe = UniverseManager(
        snapshot_path=tmp_path / "snapshot.json",
        fallback_condition_name="test",
        strategy_universe_config={
            "bottom_reversal": {"use_snapshot": True, "use_condition": False}
        },
        external_candidate_path=path,
    )
    universe.replace_snapshot_rows(
        [{"symbol": "SNAP", "strategies": ["bottom_reversal"]}]
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidates": [
                    {
                        "symbol": "005930",
                        "name": "Samsung",
                        "selection_date": "2026-09-11",
                        "strategy_tag": "bottom_reversal",
                        "intended_holding_period": "3-10d",
                        "source": "test",
                        "expires_at": "2026-09-12T09:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    universe.load_external_candidates(
        as_of=datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc)
    )
    path.write_text("{", encoding="utf-8")
    universe.calls = []
    app = _app(monkeypatch, True, universe)

    assert app.load_external_candidates_and_subscribe() == []
    assert universe.external_codes() == []
    assert universe.strategy_codes("bottom_reversal") == ["SNAP"]
    assert universe.should_route("HELD", has_position=True) is True
    assert universe.should_route("PENDING", has_open_order=True) is True


@pytest.mark.parametrize("enabled", [False, True])
def test_init_configures_provider_only_when_enabled(monkeypatch, tmp_path, enabled):
    captured = {}

    class FakeApplication:
        def __init__(self, _args):
            pass

    class FakeStore:
        def __init__(self, **_kwargs):
            pass

    class FakeBroker:
        def __init__(self, **_kwargs):
            pass

    class FakeEngine:
        def __init__(self, *_args, **_kwargs):
            pass

    class FakeStrategy:
        def __init__(self, config):
            self.config = config

    class FakeTimer:
        pass

    class CapturingUniverse(UniverseManager):
        def __init__(self, **kwargs):
            captured.update(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(main_live, "QApplication", FakeApplication)
    monkeypatch.setattr(main_live, "SQLiteStore", FakeStore)
    monkeypatch.setattr(main_live, "KiwoomBroker", FakeBroker)
    monkeypatch.setattr(main_live, "TradingEngine", FakeEngine)
    monkeypatch.setattr(main_live, "MomentumIntradayStrategy", FakeStrategy)
    monkeypatch.setattr(main_live, "UniverseManager", CapturingUniverse)
    monkeypatch.setattr(main_live, "QTimer", FakeTimer)
    monkeypatch.setattr(main_live, "setup_logger", lambda _name: FakeLogger())
    monkeypatch.setattr(main_live.MainLiveApp, "_build_telegram", lambda self: None)
    monkeypatch.setattr(main_live.config, "ENABLE_EXTERNAL_UNIVERSE", enabled)
    monkeypatch.setattr(main_live.config, "EXTERNAL_CANDIDATE_FILE", str(tmp_path / "candidates.json"))

    app = main_live.MainLiveApp()

    expected = tmp_path / "candidates.json" if enabled else None
    assert captured["external_candidate_path"] == expected
    assert (app.universe.external_candidate_provider is not None) is enabled


def test_boot_loads_external_after_sync_and_snapshot_before_condition(monkeypatch):
    app = object.__new__(main_live.MainLiveApp)
    calls = []

    class Signal:
        def connect(self, _callback):
            pass

    class Timer:
        timeout = Signal()

        def start(self, _interval):
            pass

    class Broker:
        def set_condition_initial_callback(self, _callback):
            pass

        def set_condition_realtime_callback(self, _callback):
            pass

        def set_real_tick_callback(self, _callback):
            pass

        def show_account_window(self):
            pass

    class Engine:
        def start(self):
            pass

        def sync_account(self, password=""):
            calls.append("account")

        def sync_pending_orders(self, password=""):
            calls.append("pending")

        def health_check(self):
            calls.append("health")

        def manage_pending_orders(self):
            pass

    app.logger = FakeLogger()
    app.shutting_down = False
    app.booting = True
    app.broker = Broker()
    app.engine = Engine()
    app.heartbeat = Timer()
    app.shutdown_timer = Timer()
    app.order_manage_timer = Timer()
    app.condition_timer = Timer()
    app.app = SimpleNamespace(exec_=lambda: 0)
    app.log_run_mode = lambda: calls.append("mode")
    app.auto_shutdown = lambda: None
    app._start_shutdown_watchdog = lambda: None
    app._refresh_real_registration = lambda: None
    app.load_snapshot_and_subscribe = lambda: calls.append("snapshot")
    app.load_external_candidates_and_subscribe = lambda: calls.append("external")
    app.maybe_start_condition_search = lambda: calls.append("condition")

    monkeypatch.setattr(main_live.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(main_live.QTimer, "singleShot", lambda *_args: None, raising=False)
    monkeypatch.setattr(main_live.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(main_live.sys, "exit", lambda code: calls.append(("exit", code)))
    monkeypatch.setattr(app, "_msec_until_today_hhmm", lambda _hhmm: 0)

    app.boot()

    assert calls.index("account") < calls.index("pending")
    assert calls.index("pending") < calls.index("snapshot")
    assert calls.index("snapshot") < calls.index("external")
    assert calls.index("external") < calls.index("condition")
