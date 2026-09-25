"""Run one manually-authorized, read-only Kiwoom TR in a child process.

The login window, account selection, and any account password are handled by
the operator. This process never calls SendOrder, amend, or cancel methods and
does not write response payloads to disk.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication, QInputDialog, QLineEdit

TR_TIMEOUT_SECONDS = 120
TR_PREV_NEXT_INDEX = 4
TR_NAME_INDEX = 1
RECORD_NAME_INDEX = 2
SCREEN_BY_TR = {
    "opw00018": "9101",
    "opt10075": "9102",
}


@dataclass
class QueryEvidence:
    """Metadata for one request without retaining account or row contents."""

    requested_at: str
    responded_at: str | None = None
    request_return: int | None = None
    pages: list[dict[str, object]] | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        """Initialize the page collection when omitted by the caller."""
        if self.pages is None:
            self.pages = []


def now() -> str:
    """Return an unambiguous UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def safe_message_present(message: str) -> bool:
    """Avoid printing broker text that could contain account-related data."""
    return bool(re.search(r"\S", message))


def parse_args() -> argparse.Namespace:
    """Parse exactly one approved candidate TR."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tr", choices=("opw00018", "opt10075", "opw00007"), required=True
    )
    parser.add_argument("--timeout", type=int, default=TR_TIMEOUT_SECONDS)
    return parser.parse_args()


def login(control: QAxWidget, timeout_seconds: int) -> tuple[bool, int | None, str]:
    """Open the broker login UI and wait for its connection event."""
    state = int(control.dynamicCall("GetConnectState()"))
    if state == 1:
        return True, 0, "already_connected"

    event_loop = QEventLoop()
    login_error: int | None = None

    def on_connect(error_code: int) -> None:
        nonlocal login_error
        login_error = int(error_code)
        event_loop.quit()

    control.OnEventConnect.connect(on_connect)
    comm_connect_return = int(control.dynamicCall("CommConnect()"))
    if comm_connect_return != 0:
        return False, comm_connect_return, "COMM_CONNECT_RETURN"
    QTimer.singleShot(timeout_seconds * 1000, event_loop.quit)
    event_loop.exec()
    connected = int(control.dynamicCall("GetConnectState()")) == 1
    if not connected and login_error is None:
        return False, None, "LOGIN_TIMEOUT"
    return connected, login_error, "LOGIN_EVENT"


def choose_account(control: QAxWidget) -> tuple[str, str] | None:
    """Let the operator choose an account without displaying account numbers."""
    raw_accounts = str(control.dynamicCall("GetLoginInfo(QString)", "ACCNO"))
    accounts = [value for value in raw_accounts.split(";") if value]
    if not accounts:
        print("account_count 0", flush=True)  # noqa: T201
        return None
    print("account_count", len(accounts), flush=True)  # noqa: T201
    labels = [f"Account {index + 1}" for index in range(len(accounts))]
    selected, accepted = QInputDialog.getItem(
        None,
        "Read-only account selection",
        "Choose an account (numbers are hidden):",
        labels,
        current=0,
        editable=False,
    )
    if not accepted:
        return None
    index = labels.index(selected)
    return accounts[index], f"READONLY-ACCOUNT-{index + 1}"


def configure_request(
    control: QAxWidget, tr_code: str, account_number: str
) -> str | None:
    """Apply only the verified candidate inputs for one TR."""
    if tr_code == "opw00018":
        password, accepted = QInputDialog.getText(
            None,
            "Read-only query authentication",
            "Enter the account password (not stored or printed):",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return "ACCOUNT_PASSWORD_NOT_PROVIDED"
        values = {
            "계좌번호": account_number,
            "비밀번호": password,
            "비밀번호입력매체구분": "00",
            "조회구분": "1",
        }
    elif tr_code == "opt10075":
        values = {
            "계좌번호": account_number,
            "전체종목구분": "0",
            "매매구분": "0",
            "종목코드": "",
            "체결구분": "1",
        }
    else:
        return "TR_SPEC_UNCONFIRMED"
    for name, value in values.items():
        control.dynamicCall("SetInputValue(QString, QString)", name, value)
    return None


def query_one(control: QAxWidget, tr_code: str, timeout_seconds: int) -> QueryEvidence:
    """Request one TR and retain page metadata only."""
    evidence = QueryEvidence(requested_at=now())
    event_loop = QEventLoop()
    request_name = f"readonly_{tr_code}"
    screen = SCREEN_BY_TR[tr_code]
    response_error: str | None = None

    def on_message(*args: object) -> None:
        nonlocal response_error
        response_error = (
            "BROKER_MESSAGE_PRESENT"
            if args and safe_message_present(str(args[-1]))
            else None
        )

    def on_data(*args: object) -> None:
        previous_next = (
            str(args[TR_PREV_NEXT_INDEX]).strip()
            if len(args) > TR_PREV_NEXT_INDEX
            else "UNKNOWN"
        )
        tr_name = str(args[TR_NAME_INDEX]) if len(args) > TR_NAME_INDEX else tr_code
        record_name = (
            str(args[RECORD_NAME_INDEX])
            if len(args) > RECORD_NAME_INDEX
            else request_name
        )
        row_count = int(
            control.dynamicCall("GetRepeatCnt(QString, QString)", tr_name, record_name)
        )
        evidence.pages.append(
            {
                "page_number": len(evidence.pages) + 1,
                "received_at": now(),
                "prev_next": previous_next,
                "row_count": row_count,
                "complete": previous_next in {"", "0"},
            }
        )
        if previous_next == "2":
            evidence.request_return = int(
                control.dynamicCall(
                    "CommRqData(QString, QString, int, QString)",
                    request_name,
                    tr_code,
                    2,
                    screen,
                )
            )
            if evidence.request_return != 0:
                evidence.error = f"COMM_RQ_DATA_RETURN_{evidence.request_return}"
                event_loop.quit()
            return
        evidence.responded_at = now()
        evidence.error = response_error
        event_loop.quit()

    control.OnReceiveMsg.connect(on_message)
    control.OnReceiveTrData.connect(on_data)
    evidence.request_return = int(
        control.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            request_name,
            tr_code,
            0,
            screen,
        )
    )
    if evidence.request_return != 0:
        evidence.error = f"COMM_RQ_DATA_RETURN_{evidence.request_return}"
        return evidence
    QTimer.singleShot(timeout_seconds * 1000, event_loop.quit)
    event_loop.exec()
    if evidence.responded_at is None:
        evidence.error = evidence.error or "TR_TIMEOUT_OR_INCOMPLETE"
    return evidence


def main() -> int:
    """Run login and at most one read-only query."""
    args = parse_args()
    app = QApplication([])
    control = QAxWidget()
    created = control.setControl("KHOPENAPI.KHOpenAPICtrl.1")
    if not created:
        print("control_created False; TR_NOT_CALLED", flush=True)  # noqa: T201
        return 1
    connected, login_error, login_status = login(control, args.timeout)
    print(  # noqa: T201
        "login_status",
        login_status,
        "login_error",
        login_error,
        "connected",
        connected,
        flush=True,
    )
    if not connected:
        control.clear()
        return 2
    account = choose_account(control)
    if account is None:
        print("account_selection_failed; TR_NOT_CALLED", flush=True)  # noqa: T201
        control.clear()
        return 3
    account_number, alias = account
    configuration_error = configure_request(control, args.tr, account_number)
    if configuration_error:
        print(configuration_error, "TR_NOT_CALLED", flush=True)  # noqa: T201
        control.clear()
        return 4
    evidence = query_one(control, args.tr, args.timeout)
    print(  # noqa: T201
        "tr",
        args.tr,
        "alias",
        alias,
        "requested_at",
        evidence.requested_at,
        "responded_at",
        evidence.responded_at,
        "pages",
        evidence.pages,
        "error",
        evidence.error,
        flush=True,
    )
    control.clear()
    app.processEvents()
    app.quit()
    return 0 if evidence.responded_at and evidence.error is None else 5


if __name__ == "__main__":
    raise SystemExit(main())
