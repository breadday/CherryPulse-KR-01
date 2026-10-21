"""A read-only probe must never execute by default or expose broker rows."""

import pytest

from adapters.kiwoom_rest_readonly import RestPage, RestQuery
from tools.probe_kiwoom_rest import main


def test_default_does_not_read_keys_or_use_network(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert '"network": false' in output
    assert "EXECUTION_NOT_REQUESTED" in output


def test_missing_keys_fails_without_echo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CHERRYPULSE_PAPER_APP_KEY", raising=False)
    monkeypatch.delenv("KIWOOM_APP_KEY", raising=False)
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    assert main(["--execute-read-only"]) == 1
    output = capsys.readouterr().out
    assert "private-secret" not in output
    assert "SETUP_OR_AUTH_UNCONFIRMED" in output


def test_kiwoom_env_fallback_serves_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CHERRYPULSE_PAPER_APP_KEY", raising=False)
    monkeypatch.delenv("CHERRYPULSE_PAPER_APP_SECRET", raising=False)
    monkeypatch.setenv("KIWOOM_APP_KEY", "kiwoom-key")
    monkeypatch.setenv("KIWOOM_APP_SECRET", "kiwoom-secret")

    def fetch(
        _self: object,
        _query: RestQuery,
        _body: dict[str, str],
        _cont: str,
        _cursor: str,
    ) -> RestPage:
        return RestPage(
            {
                "return_code": 0,
                "acnt_evlt_remn_indv_tot": [{"acnt_no": "private-account"}],
                "oso": [],
            },
            "N",
            "",
        )

    monkeypatch.setattr(
        "tools.probe_kiwoom_rest.PaperReadOnlyTransport.fetch_page", fetch
    )
    assert main(["--execute-read-only"]) == 0
    output = capsys.readouterr().out
    assert all(secret not in output for secret in ["kiwoom-key", "kiwoom-secret"])


def test_success_reports_counts_without_accounts_or_tokens(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    def fetch(
        _self: object, query: RestQuery, _body: dict[str, str], _cont: str, _cursor: str
    ) -> RestPage:
        calls.append(query.value)
        return RestPage(
            {
                "return_code": 0,
                "acnt_evlt_remn_indv_tot": [{"acnt_no": "private-account"}],
                "oso": [],
            },
            "N",
            "",
        )

    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    monkeypatch.setattr(
        "tools.probe_kiwoom_rest.PaperReadOnlyTransport.fetch_page", fetch
    )
    assert main(["--execute-read-only"]) == 0
    output = capsys.readouterr().out
    assert calls == ["kt00018", "ka10075"]
    assert '"account_reconciled": false' in output
    assert all(
        secret not in output
        for secret in ["private-account", "private-key", "private-secret"]
    )


def test_history_opt_in_reads_five_queries_without_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    def fetch(
        _self: object, query: RestQuery, _body: dict[str, str], _cont: str, _cursor: str
    ) -> RestPage:
        calls.append(query.value)
        return RestPage(
            {
                "return_code": 0,
                "acnt_evlt_remn_indv_tot": [],
                "oso": [],
                "acnt_ord_cntr_prps_dtl": [],
                "acnt_ord_cntr_prst_array": [],
                "cntr": [],
            },
            "N",
            "",
        )

    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    monkeypatch.setattr(
        "tools.probe_kiwoom_rest.PaperReadOnlyTransport.fetch_page", fetch
    )
    assert main(["--execute-read-only", "--include-history"]) == 0
    output = capsys.readouterr().out
    assert calls == ["kt00018", "ka10075", "kt00007", "kt00009", "ka10076"]
    assert '"account_reconciled": false' in output
    assert "private-key" not in output
    assert "private-secret" not in output


def test_failed_query_returns_nonzero_without_raw_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    monkeypatch.setattr(
        "tools.probe_kiwoom_rest.PaperReadOnlyTransport.fetch_page",
        lambda *_: RestPage(
            {"return_code": 3, "return_msg": "private-secret"}, "N", ""
        ),
    )
    assert main(["--execute-read-only"]) == 1
    output = capsys.readouterr().out
    assert "private-secret" not in output
    assert "API_SUCCESS_UNCONFIRMED" in output


@pytest.mark.parametrize("limit", ["0", "11", "-1"])
def test_limits_checked_before_execution(limit: str) -> None:
    with pytest.raises(SystemExit):
        main(["--execute-read-only", "--max-pages", limit])


def test_auth_failure_stops_before_second_query(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[int] = []

    def issue(_self: object, _credentials: object) -> dict[str, object]:
        calls.append(1)
        raise TimeoutError("synthetic-auth-error")

    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    monkeypatch.setattr("tools.probe_kiwoom_rest.PaperTokenIssuer.issue", issue)
    assert main(["--execute-read-only"]) == 1
    assert calls == [1]
    assert "synthetic-auth-error" not in capsys.readouterr().out


def test_malformed_payload_still_returns_sanitized_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    monkeypatch.setattr(
        "tools.probe_kiwoom_rest.PaperReadOnlyTransport.fetch_page",
        lambda *_: RestPage(None, "N", ""),
    )  # type: ignore[arg-type]
    assert main(["--execute-read-only"]) == 1
    assert "RESPONSE_INVALID" in capsys.readouterr().out
