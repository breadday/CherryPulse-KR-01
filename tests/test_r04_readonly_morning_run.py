from datetime import UTC, datetime

from tools.r04_readonly_morning_run import (
    fixed_commands,
    market_gate,
    sanitize_rest_report,
    sanitize_ws_report,
)


def test_sanitized_rest_report_keeps_five_safe_query_summaries() -> None:
    report = sanitize_rest_report(
        {
            "mode": "PAPER",
            "orders_enabled": False,
            "account_reconciled": False,
            "queries": [
                {
                    "api_id": api_id,
                    "complete": True,
                    "reason": "QUERY_COMPLETE_ONLY",
                    "pages": 1,
                    "observed_rows": 0,
                    "account_no": "must-not-survive",
                }
                for api_id in ("kt00018", "ka10075", "kt00007", "kt00009", "ka10076")
            ],
            "token": "must-not-survive",
        }
    )

    assert report == {
        "queries": [
            {
                "api_id": api_id,
                "complete": True,
                "reason": "QUERY_COMPLETE_ONLY",
                "pages": 1,
                "observed_rows": 0,
            }
            for api_id in ("kt00018", "ka10075", "kt00007", "kt00009", "ka10076")
        ],
        "orders_enabled": False,
        "account_reconciled": False,
    }


def test_sanitized_ws_report_keeps_only_live_evidence() -> None:
    report = sanitize_ws_report(
        {
            "reason": "QUOTE_OBSERVED",
            "connections": 1,
            "quotes_observed": 3,
            "malformed_frames": 0,
            "fresh_before_close": True,
            "orders_enabled": False,
            "account_reconciled": False,
            "raw_frame": "must-not-survive",
            "token": "must-not-survive",
        }
    )

    assert report == {
        "reason": "QUOTE_OBSERVED",
        "connections": 1,
        "quotes_observed": 3,
        "malformed_frames": 0,
        "fresh_before_close": True,
        "orders_enabled": False,
        "account_reconciled": False,
    }


def test_market_gate_never_labels_weekend_or_after_hours_as_live() -> None:
    assert market_gate(datetime(2026, 11, 6, 1, 0, tzinfo=UTC)) == "MARKET_OPEN"
    assert market_gate(datetime(2026, 11, 7, 1, 0, tzinfo=UTC)) == "WEEKEND"
    assert market_gate(datetime(2026, 11, 6, 7, 0, tzinfo=UTC)) == "AFTER_CLOSE"


def test_fixed_commands_only_invoke_readonly_probes() -> None:
    rest, websocket = fixed_commands("python.exe")
    assert rest == [
        "python.exe",
        "-m",
        "tools.probe_kiwoom_rest",
        "--execute-read-only",
        "--max-pages",
        "3",
        "--include-history",
    ]
    assert websocket == [
        "python.exe",
        "-m",
        "tools.probe_kiwoom_ws",
        "005930",
        "--seconds",
        "30",
        "--execute-read-only",
    ]
    order_controls = ("order", "cancel")
    assert not any(
        control in arg.lower() for arg in rest + websocket for control in order_controls
    )
