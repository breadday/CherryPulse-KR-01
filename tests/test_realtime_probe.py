"""Exercise the standalone quote probe without a Windows OCX or an account."""

from __future__ import annotations

import contextlib
import io
import runpy
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from tools.inspect_kiwoom_realtime import seconds_until_start_at

if TYPE_CHECKING:
    from collections.abc import Callable


def _fake_pyqt_modules(
    widget: Callable[..., object],
    timer: Callable[..., object],
    application: Callable[..., object],
) -> dict[str, types.ModuleType]:
    """Expose probe fakes under the PyQt5 import names."""
    fake_modules: dict[str, types.ModuleType] = {"PyQt5": types.ModuleType("PyQt5")}
    for submodule, attribute, value in (
        ("QAxContainer", "QAxWidget", widget),
        ("QtCore", "QTimer", timer),
        ("QtWidgets", "QApplication", application),
    ):
        module = types.ModuleType(f"PyQt5.{submodule}")
        setattr(module, attribute, value)
        fake_modules[module.__name__] = module
    return fake_modules


def _assert_no_order_api(calls: list[tuple[str, tuple[object, ...]]]) -> None:
    """Forbid order, TR, and login-info calls on the recording surface."""
    assert not any(
        "Order" in method or "CommRqData" in method or "GetLoginInfo" in method
        for method, _ in calls
    )


def _fake_real_data(
    calls: list[tuple[str, tuple[object, ...]]], method: str, args: tuple[object, ...]
) -> object:
    """Record one virtual OCX call and answer real-data reads with fixed FIDs."""
    calls.append((method, args))
    if method.startswith("GetCommRealData"):
        return {10: "+070000", 20: "091501", 290: "2", 9081: "1"}[cast("int", args[1])]
    return 0


def _run_probe() -> tuple[str, list[tuple[str, tuple[object, ...]]], list[int]]:
    """Drive the probe against virtual Qt fakes and return its record."""
    calls: list[tuple[str, tuple[object, ...]]] = []
    timers: list[tuple[int, Callable[[], None]]] = []
    scheduled: list[int] = []
    control: Widget | None = None

    class Signal:
        callback: Callable[..., None] | None = None

        def connect(self, callback: Callable[..., None]) -> None:
            self.callback = callback

    class Widget:
        def __init__(self, _name: str) -> None:
            nonlocal control
            self.OnEventConnect = Signal()
            self.OnReceiveRealData = Signal()
            control = self

        def isNull(self) -> bool:  # noqa: N802 - mirrors QAxWidget.isNull.
            return False

        def dynamicCall(self, method: str, *args: object) -> object:  # noqa: N802 - mirrors QAxWidget.dynamicCall.
            return _fake_real_data(calls, method, args)

    class Application:
        def __init__(self, _argv: list[str]) -> None:
            self.finished = False

        def quit(self) -> None:
            self.finished = True

        def exec_(self) -> None:
            assert control is not None
            assert control.OnEventConnect.callback is not None
            assert control.OnReceiveRealData.callback is not None
            control.OnEventConnect.callback(0)
            control.OnReceiveRealData.callback("000660", "주식체결", "")
            control.OnReceiveRealData.callback("005930", "주식시세", "")
            control.OnReceiveRealData.callback("005930", "주식체결", "")
            control.OnReceiveRealData.callback("005930", "주식체결", "")
            while not self.finished:
                _, callback = timers.pop(0)
                callback()

    class Timer:
        @staticmethod
        def singleShot(milliseconds: int, callback: Callable[[], None]) -> None:  # noqa: N802 - mirrors QTimer.singleShot.
            scheduled.append(milliseconds)
            timers.append((milliseconds, callback))

    fake_modules = _fake_pyqt_modules(Widget, Timer, Application)

    path = Path(__file__).resolve().parents[1] / "tools/inspect_kiwoom_realtime.py"
    stdout = io.StringIO()
    with (
        patch.dict(sys.modules, fake_modules),
        patch.object(sys, "argv", ["probe", "005930", "--seconds", "30"]),
        contextlib.redirect_stdout(stdout),
        pytest.raises(SystemExit) as caught,
    ):
        runpy.run_path(str(path), run_name="__main__")

    assert caught.value.code == 0
    return stdout.getvalue(), calls, scheduled


class ProbeBoundaryTest(unittest.TestCase):
    """An event callback can only inspect quotes and remove its subscription."""

    def test_manual_login_can_wait_for_a_same_day_market_observation(self) -> None:
        morning = datetime(2026, 9, 28, 7, 0, tzinfo=timezone(timedelta(hours=9)))
        target, delay = seconds_until_start_at("09:05", morning)
        assert (target.hour, target.minute, delay) == (9, 5, 7_500)
        for invalid in ("9:05", "25:00", "06:59", "23:59"):
            with pytest.raises(ValueError, match="start time must be"):
                seconds_until_start_at(invalid, morning)

    def test_trade_callbacks_are_filtered(self) -> None:
        stdout, calls, scheduled = _run_probe()
        assert scheduled == [60_000, 30_000]
        assert "event_seq=1" in stdout
        assert "event_seq=2" in stdout
        assert "fid10='+070000'" in stdout
        assert "fid20='091501'" in stdout
        assert "stock-trade events=2" in stdout
        assert sum(method.startswith("GetCommRealData") for method, _ in calls) == 8
        assert sum(method.startswith("SetRealRemove") for method, _ in calls) == 1

    def test_trade_callbacks_never_call_order_api(self) -> None:
        _, calls, _ = _run_probe()
        _assert_no_order_api(calls)


if __name__ == "__main__":
    unittest.main()
