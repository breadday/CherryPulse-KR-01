"""Manual quote-only KOA evidence probe; never routes data to the engine."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime


def main() -> int:
    parser = argparse.ArgumentParser(description="Observe raw stock-trade FIDs without orders or DB")
    parser.add_argument("symbol", help="one six-digit KRX stock code")
    parser.add_argument("--seconds", type=int, default=30, help="observation timeout (1-120)")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]{6}", args.symbol) or not 1 <= args.seconds <= 120:
        parser.error("use a six-digit symbol and 1-120 seconds")

    # Import only after validating arguments. Windows 32-bit Python and the
    # installed KHOPENAPI ActiveX control are required to run this probe.
    from PyQt5.QAxContainer import QAxWidget
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    control = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
    if control.isNull():
        print("OpenAPI control unavailable; check 32-bit Python and installation", file=sys.stderr)
        return 2

    screen = "8799"
    registered = False
    exit_code = 0
    event_count = 0

    def finish() -> None:
        nonlocal registered
        if registered:
            control.dynamicCall("SetRealRemove(QString, QString)", screen, args.symbol)
            registered = False
        print(f"observation ended; stock-trade events={event_count}", flush=True)
        app.quit()

    def on_real(code: str, real_type: str, _payload: str) -> None:
        nonlocal event_count
        if code != args.symbol or real_type != "주식체결":
            return
        event_count += 1
        # Read FIDs inside the event callback as prescribed by the installed guide.
        price = control.dynamicCall("GetCommRealData(QString, int)", code, 10)
        trade_time = control.dynamicCall("GetCommRealData(QString, int)", code, 20)
        market = control.dynamicCall("GetCommRealData(QString, int)", code, 290)
        exchange = control.dynamicCall("GetCommRealData(QString, int)", code, 9081)
        received = datetime.now().astimezone().isoformat(timespec="microseconds")
        print(
            f"received={received} code={code!r} type={real_type!r} "
            f"fid10={price!r} fid20={trade_time!r} "
            f"fid290={market!r} fid9081={exchange!r}",
            flush=True,
        )

    def on_connect(error: int) -> None:
        nonlocal exit_code, registered
        if error != 0:
            print(f"login failed: {error}", file=sys.stderr)
            exit_code = 2
            app.quit()
            return
        result = control.dynamicCall(
            "SetRealReg(QString, QString, QString, QString)",
            screen,
            args.symbol,
            "10;20;290;9081",
            "0",
        )
        if result != 0:
            print(f"real-time subscription failed: {result}", file=sys.stderr)
            exit_code = 2
            app.quit()
            return
        registered = True
        print("observing stock trades; Ctrl+C or timeout stops subscription", flush=True)
        QTimer.singleShot(args.seconds * 1000, finish)

    def on_login_timeout() -> None:
        nonlocal exit_code
        if not registered:
            print("login/registration timed out after 60 seconds", file=sys.stderr)
            exit_code = 2
            app.quit()

    control.OnEventConnect.connect(on_connect)
    control.OnReceiveRealData.connect(on_real)
    QTimer.singleShot(60_000, on_login_timeout)
    result = control.dynamicCall("CommConnect()")
    if result != 0:
        print(f"login request failed: {result}", file=sys.stderr)
        return 2
    try:
        app.exec_()
    except KeyboardInterrupt:
        pass
    finally:
        if registered:
            control.dynamicCall("SetRealRemove(QString, QString)", screen, args.symbol)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
