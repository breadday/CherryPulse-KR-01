"""Safe WebSocket failure summaries keep exception detail out of manifests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from tools import probe_kiwoom_ws, r045_morning_run


def test_probe_setup_failure_emits_only_fixed_safe_codes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_setup() -> object:
        raise ValueError("private credential detail")  # noqa: TRY003 -- Redaction sentinel.

    monkeypatch.setattr(probe_kiwoom_ws, "paper_credentials_from_env", fail_setup)

    assert probe_kiwoom_ws.main(["005930", "--execute-read-only"]) == 1
    report = json.loads(capsys.readouterr().out)

    assert report["failure_stage"] == "SETUP"
    assert report["failure_kind"] == "VALUE_ERROR"
    assert "private" not in json.dumps(report)


def test_manifest_allowlist_keeps_failure_codes_but_not_free_text() -> None:
    report = json.dumps(
        {
            "failure_stage": "CONNECT",
            "failure_kind": "OS_ERROR",
            "failure_message": "secret-bearing detail",
        }
    )

    assert r045_morning_run._safe_diagnostic(report) == {  # noqa: SLF001
        "failure_stage": "CONNECT",
        "failure_kind": "OS_ERROR",
    }
    assert (
        r045_morning_run._safe_diagnostic(  # noqa: SLF001
            json.dumps({"failure_stage": "secret", "failure_kind": "other"})
        )
        == {}
    )
