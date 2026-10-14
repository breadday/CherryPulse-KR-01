"""Paper order demo stays preview-first, single-submit, and identifier-silent."""

import json
from io import BytesIO
from pathlib import Path
from urllib.request import Request

import pytest

from adapters.kiwoom_rest_order import (
    BUY_API_ID,
    MOCK_ORDER_URL,
    BuyPreview,
    build_buy_body,
    classify_order_response,
)
from adapters.kiwoom_rest_readonly import RestPage, RestQuery
from tools import submit_paper_buy, verify_paper_linkage
from tools.submit_paper_buy import submit_buy_body


def test_preview_validation() -> None:
    assert build_buy_body(BuyPreview("005930", "70000")) == {
        "dmst_stex_tp": "KRX",
        "stk_cd": "005930",
        "ord_qty": "1",
        "trde_tp": "0",
        "ord_uv": "70000",
        "cond_uv": "",
    }
    for symbol, price, reason in [
        ("5930", "70000", "ORDER_SYMBOL_INVALID"),
        ("005930", "market", "ORDER_PRICE_INVALID"),
        ("005930", "0", "ORDER_PRICE_INVALID"),
        ("005930", "100001", "ORDER_PRICE_CAPPED"),
    ]:
        with pytest.raises(ValueError, match=reason):
            BuyPreview(symbol, price)


def test_classify_order_response() -> None:
    assert classify_order_response({"return_code": 0, "ord_no": "1"}) == (
        True,
        "ORDER_ACKED",
    )
    assert classify_order_response({"return_code": "0", "ord_no": "1"}) == (
        True,
        "ORDER_ACKED",
    )
    assert classify_order_response({"return_code": 3})[1] == "API_SUCCESS_UNCONFIRMED"
    assert classify_order_response({"return_code": 0})[1] == "ORDER_NUMBER_MISSING"
    assert classify_order_response(None)[1] == "RESPONSE_INVALID"


def test_preview_needs_no_keys_or_network(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CHERRYPULSE_PAPER_APP_KEY", raising=False)
    monkeypatch.delenv("CHERRYPULSE_PAPER_APP_SECRET", raising=False)
    assert submit_paper_buy.main(["--symbol", "005930", "--price", "70000"]) == 0
    output = capsys.readouterr().out
    assert '"network": false' in output
    assert "EXECUTION_NOT_REQUESTED" in output


def test_preview_rejects_bad_price(capsys: pytest.CaptureFixture[str]) -> None:
    assert submit_paper_buy.main(["--price", "100001"]) == 1
    assert "ORDER_PRICE_CAPPED" in capsys.readouterr().out


class FakeOpener:
    """Capture the order request and answer with a canned payload."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.requests: list[Request] = []

    def open(self, request: Request, *, timeout: float) -> BytesIO:
        """Record one request without touching the network."""
        assert timeout == 10
        self.requests.append(request)
        return BytesIO(self.payload)


def canned(payload: dict[str, object]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def arm_submit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: bytes
) -> FakeOpener:
    """Isolate the submit tool root, keys, and opener for one execution."""
    monkeypatch.setattr(submit_paper_buy, "ROOT", tmp_path)
    opener = FakeOpener(payload)
    monkeypatch.setattr(submit_paper_buy, "real_opener", lambda: opener)
    monkeypatch.setattr(
        submit_paper_buy.PaperTokenCache, "get", lambda _self: "synthetic-token"
    )
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    return opener


def submit_argv() -> list[str]:
    return ["--symbol", "005930", "--price", "70000", "--confirm-execute"]


def test_submit_posts_once_to_mock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    opener = arm_submit(
        monkeypatch, tmp_path, canned({"return_code": 0, "ord_no": "private-ord"})
    )
    payload = submit_buy_body(
        build_buy_body(BuyPreview("005930", "70000")),
        "synthetic-token",
        submit_paper_buy.RequestPacer(),
        10,
        lambda: opener,
    )
    assert classify_order_response(payload)[0] is True
    assert opener.requests[0].full_url == MOCK_ORDER_URL
    assert opener.requests[0].get_header("Api-id") == BUY_API_ID


def test_submit_ack_writes_sentinel_without_identifiers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    opener = arm_submit(
        monkeypatch, tmp_path, canned({"return_code": 0, "ord_no": "private-ord"})
    )
    assert submit_paper_buy.main(submit_argv()) == 0
    assert len(opener.requests) == 1
    output = capsys.readouterr().out
    assert '"acked": true' in output
    assert "private-ord" not in output
    assert "private-key" not in output
    assert len(list((tmp_path / "results").glob("*"))) == 1


def test_sentinel_blocks_second_submit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    opener = arm_submit(
        monkeypatch, tmp_path, canned({"return_code": 0, "ord_no": "private-ord"})
    )
    assert submit_paper_buy.main(submit_argv()) == 0
    assert submit_paper_buy.main(submit_argv()) == 1
    assert "SECOND_ORDER_BLOCKED" in capsys.readouterr().out
    assert len(opener.requests) == 1


def test_rejection_allows_retry_without_sentinel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    opener = arm_submit(
        monkeypatch, tmp_path, canned({"return_code": 3, "return_msg": "nope"})
    )
    assert submit_paper_buy.main(submit_argv()) == 1
    assert "API_SUCCESS_UNCONFIRMED" in capsys.readouterr().out
    assert len(opener.requests) == 1
    assert not (tmp_path / "results").exists()


def test_unknown_outcome_blocks_resubmission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class BrokenOpener:
        def open(self, *_args: object, **_kwargs: object) -> BytesIO:
            raise TimeoutError("synthetic")

    monkeypatch.setattr(submit_paper_buy, "ROOT", tmp_path)
    monkeypatch.setattr(submit_paper_buy, "real_opener", BrokenOpener)
    monkeypatch.setattr(
        submit_paper_buy.PaperTokenCache, "get", lambda _self: "synthetic-token"
    )
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    assert submit_paper_buy.main(submit_argv()) == 1
    assert "TRANSPORT_UNKNOWN" in capsys.readouterr().out
    assert submit_paper_buy.main(submit_argv()) == 1
    assert "SECOND_ORDER_BLOCKED" in capsys.readouterr().out


def test_linkage_default_is_offline(capsys: pytest.CaptureFixture[str]) -> None:
    assert verify_paper_linkage.main([]) == 0
    output = capsys.readouterr().out
    assert '"network": false' in output
    assert "EXECUTION_NOT_REQUESTED" in output


def linkage_rows() -> dict[str, list[dict[str, object]]]:
    """One synthetic open order visible in three queries, unfilled."""
    row = {
        "stk_cd": "005930",
        "ord_no": "private-ord",
        "ori_ord": "",
        "orig_ord_no": "",
    }
    return {
        "kt00007": [dict(row)],
        "kt00009": [dict(row, cntr_no="")],
        "ka10076": [],
        "ka10075": [dict(row)],
    }


def test_linkage_consistent_without_identifiers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = linkage_rows()
    row_keys = {
        "kt00007": "acnt_ord_cntr_prps_dtl",
        "kt00009": "acnt_ord_cntr_prst_array",
        "ka10076": "cntr",
        "ka10075": "oso",
    }

    def fetch(
        _self: object, query: RestQuery, _body: dict[str, str], _cont: str, _cursor: str
    ) -> RestPage:
        return RestPage(
            {"return_code": 0, row_keys[query.value]: tables[query.value]}, "N", ""
        )

    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    monkeypatch.setattr(
        "tools.verify_paper_linkage.PaperReadOnlyTransport.fetch_page", fetch
    )
    assert verify_paper_linkage.main(["--execute-read-only"]) == 0
    output = capsys.readouterr().out
    assert "LINKAGE_CONSISTENT" in output
    assert "private-ord" not in output
    assert "private-key" not in output


def test_linkage_mismatch_is_not_consistent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = linkage_rows()
    tables["kt00009"] = [
        {"stk_cd": "005930", "ord_no": "other-ord", "orig_ord_no": "", "cntr_no": ""}
    ]
    row_keys = {
        "kt00007": "acnt_ord_cntr_prps_dtl",
        "kt00009": "acnt_ord_cntr_prst_array",
        "ka10076": "cntr",
        "ka10075": "oso",
    }

    def fetch(
        _self: object, query: RestQuery, _body: dict[str, str], _cont: str, _cursor: str
    ) -> RestPage:
        return RestPage(
            {"return_code": 0, row_keys[query.value]: tables[query.value]}, "N", ""
        )

    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_KEY", "private-key")
    monkeypatch.setenv("CHERRYPULSE_PAPER_APP_SECRET", "private-secret")
    monkeypatch.setattr(
        "tools.verify_paper_linkage.PaperReadOnlyTransport.fetch_page", fetch
    )
    assert verify_paper_linkage.main(["--execute-read-only"]) == 1
    output = capsys.readouterr().out
    assert "LINKAGE_UNCONFIRMED" in output
    assert "private-ord" not in output
    assert "other-ord" not in output
