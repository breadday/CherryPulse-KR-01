import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _inert_constructor(name, calls):
    class _Inert:
        def __init__(self, *args, **kwargs):
            calls.append((name, args, kwargs))
            raise AssertionError(f"{name} was constructed during import")

    _Inert.__name__ = name
    return _Inert


def _install_inert_dependencies(monkeypatch):
    calls = []
    qt = ModuleType("PyQt5")
    qt_core = ModuleType("PyQt5.QtCore")
    qt_widgets = ModuleType("PyQt5.QtWidgets")
    qax = ModuleType("PyQt5.QAxContainer")

    qt_core.QObject = type("QObject", (), {})
    qt_core.QEventLoop = type("QEventLoop", (), {})
    qt_core.QTimer = type("QTimer", (), {})
    qt_widgets.QApplication = _inert_constructor("QApplication", calls)
    qax.QAxWidget = _inert_constructor("QAxWidget", calls)

    for name, module in {
        "PyQt5": qt,
        "PyQt5.QtCore": qt_core,
        "PyQt5.QtWidgets": qt_widgets,
        "PyQt5.QAxContainer": qax,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    if importlib.util.find_spec("requests") is None:
        requests = ModuleType("requests")

        class _Session:
            def __init__(self):
                raise AssertionError("requests.Session was constructed during import")

        requests.Session = _Session
        monkeypatch.setitem(sys.modules, "requests", requests)

    return calls


def _import_real_broker(monkeypatch):
    module_path = Path(__file__).parents[1] / "broker" / "kiwoom_broker.py"
    broker_package = importlib.import_module("broker")
    previous_attr = getattr(broker_package, "kiwoom_broker", None)
    monkeypatch.setitem(sys.modules, "broker.kiwoom_broker", None)
    monkeypatch.setattr(broker_package, "kiwoom_broker", previous_attr, raising=False)
    spec = importlib.util.spec_from_file_location("broker.kiwoom_broker", module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "broker.kiwoom_broker", module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(broker_package, "kiwoom_broker", module, raising=False)
    return module


def test_python38_imports_real_broker_and_main_without_runtime_initialization(monkeypatch):
    calls = _install_inert_dependencies(monkeypatch)
    broker = _import_real_broker(monkeypatch)

    assert broker.KiwoomBroker.__name__ == "KiwoomBroker"
    assert broker.KiwoomBroker._exec_loop_with_timeout.__annotations__["timeout_sec"] == "int | None"
    assert broker.KiwoomBroker.get_positions.__annotations__["return"] == "list[dict]"
    assert broker.KiwoomBroker.get_pending_orders.__annotations__["return"] == "list[dict]"

    main_path = Path(__file__).parents[1] / "main_live.py"
    spec = importlib.util.spec_from_file_location("_task026_main_live", main_path)
    main_live = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_live)

    assert main_live.MainLiveApp.__name__ == "MainLiveApp"
    assert calls == []


def test_shutdown_skips_account_tr_sync_outside_market_session(monkeypatch):
    _install_inert_dependencies(monkeypatch)
    main_live = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location(
            "_task026_main_live_shutdown", Path(__file__).parents[1] / "main_live.py"
        )
    )
    spec = main_live.__spec__
    spec.loader.exec_module(main_live)

    app = main_live.MainLiveApp.__new__(main_live.MainLiveApp)
    app.logger = type("Logger", (), {"info": lambda *_args: None})()
    monkeypatch.setattr(app, "_market_phase", lambda: "after_close")

    assert [name for name, _call in app._shutdown_reconciliation_calls()] == ["risk observation"]

    monkeypatch.setattr(app, "_market_phase", lambda: "market_session")
    assert [name for name, _call in app._shutdown_reconciliation_calls()] == [
        "risk observation",
        "pending sync",
        "account sync",
    ]


def test_kiwoom_text_repair_is_used_for_code_names(monkeypatch):
    _install_inert_dependencies(monkeypatch)
    broker = _import_real_broker(monkeypatch)

    class _Ocx:
        def dynamicCall(self, *_args):
            return "ÁÖ¼º¿£Áö´Ï¾î¸µ"

    instance = broker.KiwoomBroker.__new__(broker.KiwoomBroker)
    instance.ocx = _Ocx()

    assert instance.get_code_name("036930") == "주성엔지니어링"
