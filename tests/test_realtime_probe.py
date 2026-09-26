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
from typing import Callable, cast
from unittest.mock import patch

from tools.inspect_kiwoom_realtime import seconds_until_start_at


class ProbeBoundaryTest(unittest.TestCase):
    """An event callback can only inspect quotes and remove its subscription."""

    def test_manual_login_can_wait_for_a_same_day_market_observation(self) -> None:
        morning = datetime(2026, 9, 28, 7, 0, tzinfo=timezone(timedelta(hours=9)))
        target, delay = seconds_until_start_at("09:05", morning)
        self.assertEqual((target.hour, target.minute, delay), (9, 5, 7_500))
        for invalid in ("9:05", "25:00", "06:59", "23:59"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                seconds_until_start_at(invalid, morning)

    def test_trade_callbacks_are_filtered_and_never_call_order_api(self) -> None:
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

            def isNull(self) -> bool:
                return False

            def dynamicCall(self, method: str, *args: object) -> object:
                calls.append((method, args))
                if method.startswith("GetCommRealData"):
                    return {10: "+070000", 20: "091501", 290: "2", 9081: "1"}[
                        cast("int", args[1])
                    ]
                return 0

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
            def singleShot(milliseconds: int, callback: Callable[[], None]) -> None:
                scheduled.append(milliseconds)
                timers.append((milliseconds, callback))

        fake_modules = {"PyQt5": types.ModuleType("PyQt5")}
        for submodule, attribute, value in (
            ("QAxContainer", "QAxWidget", Widget),
            ("QtCore", "QTimer", Timer),
            ("QtWidgets", "QApplication", Application),
        ):
            module = types.ModuleType(f"PyQt5.{submodule}")
            setattr(module, attribute, value)
            fake_modules[module.__name__] = module

        path = Path(__file__).resolve().parents[1] / "tools/inspect_kiwoom_realtime.py"
        stdout = io.StringIO()
        with (
            patch.dict(sys.modules, fake_modules),
            patch.object(sys, "argv", ["probe", "005930", "--seconds", "30"]),
            contextlib.redirect_stdout(stdout),
        ):
            with self.assertRaises(SystemExit) as caught:
                runpy.run_path(str(path), run_name="__main__")

        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(scheduled, [60_000, 30_000])
        self.assertIn("event_seq=1", stdout.getvalue())
        self.assertIn("event_seq=2", stdout.getvalue())
        self.assertIn("fid10='+070000'", stdout.getvalue())
        self.assertIn("fid20='091501'", stdout.getvalue())
        self.assertIn("stock-trade events=2", stdout.getvalue())
        self.assertEqual(
            sum(method.startswith("GetCommRealData") for method, _ in calls), 8
        )
        self.assertEqual(
            sum(method.startswith("SetRealRemove") for method, _ in calls), 1
        )
        self.assertFalse(
            any(
                "Order" in method
                or "CommRqData" in method
                or "GetLoginInfo" in method
                for method, _ in calls
            )
        )


if __name__ == "__main__":
    unittest.main()
