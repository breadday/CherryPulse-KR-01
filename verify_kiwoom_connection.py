"""Read Kiwoom connection state without logging in or querying an account."""

from __future__ import annotations

from datetime import datetime, timezone

from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtWidgets import QApplication


def main() -> int:
    """Create the control, read GetConnectState once, and release it."""
    app = QApplication([])
    control = QAxWidget()
    created = control.setControl("KHOPENAPI.KHOpenAPICtrl.1")
    observed_at = datetime.now(timezone.utc).isoformat()
    state = int(control.dynamicCall("GetConnectState()")) if created else -1
    print(  # noqa: T201
        "observed_at",
        observed_at,
        "control_created",
        created,
        "connect_state",
        state,
        "connected",
        state == 1,
        flush=True,
    )
    control.clear()
    released = control.isNull()
    del control
    app.processEvents()
    app.quit()
    return 0 if created and released and state in {0, 1} else 1


if __name__ == "__main__":
    raise SystemExit(main())
