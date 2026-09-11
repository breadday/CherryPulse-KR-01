import json
import sys
from datetime import datetime
from types import ModuleType

import pytest


def _install_main_live_stubs():
    qt = ModuleType("PyQt5")
    qt_core = ModuleType("PyQt5.QtCore")
    qt_widgets = ModuleType("PyQt5.QtWidgets")
    qt_core.QTimer = type("QTimer", (), {})
    qt_widgets.QApplication = type("QApplication", (), {})
    broker_module = ModuleType("broker.kiwoom_broker")
    broker_module.KiwoomBroker = type("KiwoomBroker", (), {})
    telegram_module = ModuleType("infra.telegram_notifier")
    telegram_module.TelegramNotifier = type("TelegramNotifier", (), {})
    sys.modules.setdefault("PyQt5", qt)
    sys.modules.setdefault("PyQt5.QtCore", qt_core)
    sys.modules.setdefault("PyQt5.QtWidgets", qt_widgets)
    sys.modules.setdefault("broker.kiwoom_broker", broker_module)
    sys.modules.setdefault("infra.telegram_notifier", telegram_module)


_install_main_live_stubs()

import main_live
import validate_daily_snapshot


def _fixed_datetime(today):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(today.year, today.month, today.day, 9, 0, tzinfo=tz)

    return FixedDateTime


def _validate_both(monkeypatch, tmp_path, today, payload, holidays=()):
    fixed_datetime = _fixed_datetime(today)
    monkeypatch.setattr(main_live, "datetime", fixed_datetime)
    monkeypatch.setattr(validate_daily_snapshot, "datetime", fixed_datetime)
    for config in (main_live.config, validate_daily_snapshot.config):
        monkeypatch.setattr(config, "MARKET_HOLIDAYS", list(holidays))
        monkeypatch.setattr(config, "SNAPSHOT_MAX_MISSING_TRADING_DAYS", 0)
        monkeypatch.setattr(config, "SNAPSHOT_MAX_STALE_DAYS", 1)

    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    app = main_live.MainLiveApp.__new__(main_live.MainLiveApp)
    return validate_daily_snapshot.validate_snapshot(path), app._validate_snapshot_freshness(payload)


@pytest.mark.parametrize(
    "today,generated_at,latest_data_date,holidays",
    [
        (datetime(2026, 9, 14).date(), "2026-09-11 16:00:00", "2026-09-11", ()),
        (datetime(2026, 5, 26).date(), "2026-05-22 16:00:00", "2026-05-22", ("2026-05-25",)),
    ],
)
def test_previous_trading_day_snapshot_is_valid_across_closed_market_days(
    monkeypatch,
    tmp_path,
    today,
    generated_at,
    latest_data_date,
    holidays,
):
    payload = {
        "generated_at": generated_at,
        "latest_data_date": latest_data_date,
        "count": 1,
        "codes": [{"code": "005930", "last_date": latest_data_date}],
    }

    cli_result, app_result = _validate_both(monkeypatch, tmp_path, today, payload, holidays)

    assert cli_result[0] is True, cli_result[1]
    assert app_result[0] is True, app_result[1]


def test_missing_open_market_day_is_rejected(monkeypatch, tmp_path):
    payload = {
        "generated_at": "2026-09-11 16:00:00",
        "latest_data_date": "2026-09-11",
        "count": 1,
        "codes": [{"code": "005930", "last_date": "2026-09-11"}],
    }

    cli_result, app_result = _validate_both(
        monkeypatch,
        tmp_path,
        datetime(2026, 9, 15).date(),
        payload,
    )

    assert cli_result[0] is False
    assert app_result[0] is False
    assert "missing_trading_days=1" in cli_result[1]
    assert "missing_trading_days=1" in app_result[1]


@pytest.mark.parametrize(
    "generated_at,latest_data_date,expected_reason",
    [
        ("2026-09-15 16:00:00", "2026-09-14", "미래 생성일"),
        ("2026-09-14 16:00:00", "2026-09-15", "미래 일봉"),
    ],
)
def test_future_snapshot_metadata_is_rejected(
    monkeypatch,
    tmp_path,
    generated_at,
    latest_data_date,
    expected_reason,
):
    payload = {
        "generated_at": generated_at,
        "latest_data_date": latest_data_date,
        "count": 1,
        "codes": [{"code": "005930", "last_date": latest_data_date}],
    }

    cli_result, app_result = _validate_both(
        monkeypatch,
        tmp_path,
        datetime(2026, 9, 14).date(),
        payload,
    )

    assert cli_result[0] is False
    assert app_result[0] is False
    assert expected_reason in cli_result[1]
    assert expected_reason in app_result[1]
