import importlib.util
import sys
import pytest
from pathlib import Path
from types import ModuleType

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
spec = importlib.util.spec_from_file_location("_task021_kiwoom_broker", module_path)
BROKER_MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BROKER_MODULE)


class _Log:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)

    def info(self, _message):
        pass

    def error(self, _message):
        pass


class _TimerSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class _FakeTimer:
    latest = None

    def __init__(self, parent):
        self.parent = parent
        self.timeout = _TimerSignal()
        self.single_shot = False
        self.started_ms = None
        self.stopped = False
        self.deleted = False
        _FakeTimer.latest = self

    def setSingleShot(self, value):
        self.single_shot = value

    def start(self, timeout_ms):
        self.started_ms = timeout_ms

    def stop(self):
        self.stopped = True

    def deleteLater(self):
        self.deleted = True


class _Loop:
    def __init__(self, on_exec=None):
        self.running = True
        self.quit_calls = 0
        self.on_exec = on_exec

    def isRunning(self):
        return self.running

    def quit(self):
        self.quit_calls += 1
        self.running = False

    def exec_(self):
        if self.on_exec:
            self.on_exec()


def _broker(monkeypatch, loop):
    monkeypatch.setattr(BROKER_MODULE, "QTimer", _FakeTimer)
    broker = BROKER_MODULE.KiwoomBroker.__new__(BROKER_MODULE.KiwoomBroker)
    broker.logger = _Log()
    broker.tr_timeout_sec = 20
    broker.tr_loop = loop
    return broker


def test_timeout_quits_running_loop_and_reports_label(monkeypatch):
    loop = _Loop(on_exec=lambda: _FakeTimer.latest.timeout.callback())
    broker = _broker(monkeypatch, loop)

    timed_out = broker._exec_loop_with_timeout("tr_loop", "opt10075_req", 0.1)

    assert timed_out is True
    assert loop.quit_calls == 1
    assert _FakeTimer.latest.started_ms == 1000
    assert _FakeTimer.latest.single_shot is True
    assert _FakeTimer.latest.stopped is True
    assert _FakeTimer.latest.deleted is True
    assert broker.logger.warnings == ["opt10075_req 대기 시간 초과 | timeout_ms=1000"]


def test_normal_loop_completion_returns_without_timeout(monkeypatch):
    loop = _Loop(on_exec=lambda: setattr(loop, "running", False))
    broker = _broker(monkeypatch, loop)

    timed_out = broker._exec_loop_with_timeout("tr_loop", "deposit_req", 2)

    assert timed_out is False
    assert loop.quit_calls == 0
    assert _FakeTimer.latest.started_ms == 2000
    assert _FakeTimer.latest.stopped is True
    assert _FakeTimer.latest.deleted is True
    assert broker.logger.warnings == []


def test_timeout_callback_ignores_replaced_loop(monkeypatch):
    replacement = _Loop()
    loop = _Loop()
    broker = _broker(monkeypatch, loop)

    def replace_then_fire():
        broker.tr_loop = replacement
        _FakeTimer.latest.timeout.callback()

    loop.on_exec = replace_then_fire

    timed_out = broker._exec_loop_with_timeout("tr_loop", "opt10081_req", 1)

    assert timed_out is False
    assert loop.quit_calls == 0
    assert replacement.quit_calls == 0
    assert broker.logger.warnings == []


def test_missing_loop_returns_without_creating_timer(monkeypatch):
    broker = _broker(monkeypatch, None)
    _FakeTimer.latest = None

    assert broker._exec_loop_with_timeout("tr_loop", "missing", 1) is False
    assert _FakeTimer.latest is None


def test_connect_fails_when_login_event_times_out(monkeypatch):
    class _LoginLoop(_Loop):
        def exec_(self):
            _FakeTimer.latest.timeout.callback()

    class _Ocx:
        def dynamicCall(self, method, *_args):
            assert method == "CommConnect()"
            return 0

    monkeypatch.setattr(BROKER_MODULE, "QEventLoop", _LoginLoop)
    monkeypatch.setattr(BROKER_MODULE, "QTimer", _FakeTimer)
    broker = BROKER_MODULE.KiwoomBroker.__new__(BROKER_MODULE.KiwoomBroker)
    broker.logger = _Log()
    broker.ocx = _Ocx()
    broker.is_shutting_down = False
    broker.connected = False
    broker.account_no = None

    with pytest.raises(RuntimeError, match="로그인 대기 시간 초과"):
        broker.connect()
