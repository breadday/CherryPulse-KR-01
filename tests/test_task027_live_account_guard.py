import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_broker(monkeypatch):
    qt = ModuleType("PyQt5")
    qt_core = ModuleType("PyQt5.QtCore")
    qax = ModuleType("PyQt5.QAxContainer")
    qt_core.QObject = type("QObject", (), {})
    qt_core.QEventLoop = type("QEventLoop", (), {})
    qt_core.QTimer = type("QTimer", (), {})
    qax.QAxWidget = type("QAxWidget", (), {})
    for name, module in {
        "PyQt5": qt,
        "PyQt5.QtCore": qt_core,
        "PyQt5.QAxContainer": qax,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    path = Path(__file__).parents[1] / "broker" / "kiwoom_broker.py"
    spec = importlib.util.spec_from_file_location("_task027_kiwoom_broker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Log:
    def info(self, _message):
        pass


def _broker(module, account_no):
    broker = module.KiwoomBroker.__new__(module.KiwoomBroker)
    broker.logger = _Log()
    broker.account_no = account_no
    broker.is_shutting_down = False
    return broker


def test_live_connect_requires_explicit_account_number(monkeypatch):
    module = _load_broker(monkeypatch)
    monkeypatch.setattr(module.config, "ALLOW_LIVE_ORDERS", True)

    with pytest.raises(RuntimeError, match="ACCOUNT_NO"):
        _broker(module, None).connect()


def test_connect_rejects_configured_account_that_is_not_ten_digits(monkeypatch):
    module = _load_broker(monkeypatch)
    monkeypatch.setattr(module.config, "ALLOW_LIVE_ORDERS", False)

    with pytest.raises(RuntimeError, match="10자리"):
        _broker(module, "12345678").connect()


def test_server_guard_accepts_configured_paper_server(monkeypatch):
    module = _load_broker(monkeypatch)
    monkeypatch.setattr(module.config, "KIWOOM_EXPECTED_SERVER", "paper")

    module.KiwoomBroker._validate_server_environment(_broker(module, None), "1")


def test_server_guard_rejects_unexpected_server(monkeypatch):
    module = _load_broker(monkeypatch)
    monkeypatch.setattr(module.config, "KIWOOM_EXPECTED_SERVER", "paper")

    with pytest.raises(RuntimeError, match="서버 환경 불일치"):
        module.KiwoomBroker._validate_server_environment(_broker(module, None), "0")


def test_live_server_requires_explicit_confirmation(monkeypatch):
    module = _load_broker(monkeypatch)
    monkeypatch.setattr(module.config, "KIWOOM_EXPECTED_SERVER", "live")
    monkeypatch.setattr(module.config, "KIWOOM_LIVE_CONFIRMATION", "")

    with pytest.raises(RuntimeError, match="승인값"):
        module.KiwoomBroker._validate_live_confirmation(_broker(module, None))


def test_live_server_accepts_exact_confirmation(monkeypatch):
    module = _load_broker(monkeypatch)
    monkeypatch.setattr(module.config, "KIWOOM_EXPECTED_SERVER", "live")
    monkeypatch.setattr(
        module.config,
        "KIWOOM_LIVE_CONFIRMATION",
        "I_UNDERSTAND_LIVE_TRADING",
    )

    module.KiwoomBroker._validate_live_confirmation(_broker(module, None))
