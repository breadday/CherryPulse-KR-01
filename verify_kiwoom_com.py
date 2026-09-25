"""Verify the 32-bit Kiwoom ActiveX control in a child process.

This probe does not log in, start an event loop, query an account, or submit an
order.  Environment suitability is reported separately from COM success so a
missing virtual environment cannot be mistaken for an OCX creation failure.
"""

from __future__ import annotations

import struct
import sys
from importlib import metadata

from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtWidgets import QApplication

EXPECTED_POINTER_BITS = 32


def main() -> int:
    """Create and release the registered control once, then report the result."""
    print(  # noqa: T201
        "python",
        sys.version.split()[0],
        "bits",
        struct.calcsize("P") * 8,
        "isolated",
        sys.prefix != sys.base_prefix,
        flush=True,
    )
    print(  # noqa: T201
        "pyqt",
        metadata.version("PyQt5"),
        "qt",
        metadata.version("PyQt5-Qt5"),
        "sip",
        metadata.version("PyQt5-sip"),
        flush=True,
    )

    app = QApplication([])
    control = QAxWidget()
    created = control.setControl("KHOPENAPI.KHOpenAPICtrl.1")
    print(  # noqa: T201
        "control_created", created, "is_null", control.isNull(), flush=True
    )
    control.clear()
    released = control.isNull()
    print("control_released", released, flush=True)  # noqa: T201
    del control
    app.processEvents()
    app.quit()

    return (
        0
        if created and released and struct.calcsize("P") * 8 == EXPECTED_POINTER_BITS
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
