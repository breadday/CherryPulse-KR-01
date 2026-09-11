import json
from datetime import datetime, timezone

import pytest

from selectors.external_candidate_provider import (
    ExternalCandidateError,
    ExternalCandidateProvider,
)


AS_OF = datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc)


def _candidate(**overrides):
    row = {
        "symbol": "005930",
        "name": " 삼성전자 ",
        "selection_date": "2026-09-11",
        "strategy_tag": " swing ",
        "intended_holding_period": " 3-10d ",
        "source": " external-model ",
        "expires_at": "2026-09-12T09:00:00Z",
    }
    row.update(overrides)
    return row


def _write_payload(path, candidates, schema_version=1):
    path.write_text(
        json.dumps({"schema_version": schema_version, "candidates": candidates}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_load_returns_normalized_active_candidates(tmp_path):
    path = tmp_path / "candidates.json"
    _write_payload(
        path,
        [
            _candidate(),
            _candidate(symbol="000660", name="SK하이닉스", strategy_tag="vcp_box"),
        ],
    )

    candidates = ExternalCandidateProvider(path).load(as_of=AS_OF)

    assert [(item.symbol, item.strategy_tag) for item in candidates] == [
        ("005930", "swing"),
        ("000660", "vcp_box"),
    ]
    assert candidates[0].name == "삼성전자"
    assert candidates[0].intended_holding_period == "3-10d"
    assert candidates[0].source == "external-model"


def test_load_excludes_expired_candidates_at_boundary(tmp_path):
    path = tmp_path / "candidates.json"
    _write_payload(
        path,
        [
            _candidate(symbol="005930", expires_at="2026-09-11T09:00:00+00:00"),
            _candidate(symbol="000660", strategy_tag="vcp_box", expires_at="2026-09-11T09:00:01+00:00"),
        ],
    )

    candidates = ExternalCandidateProvider(path).load(as_of=AS_OF)

    assert [item.symbol for item in candidates] == ["000660"]


def test_selection_date_uses_korean_market_date(tmp_path):
    path = tmp_path / "candidates.json"
    _write_payload(path, [_candidate(selection_date="2026-09-11")])
    before_korean_market_open = datetime(2026, 9, 10, 23, 30, tzinfo=timezone.utc)

    candidates = ExternalCandidateProvider(path).load(as_of=before_korean_market_open)

    assert [item.symbol for item in candidates] == ["005930"]


@pytest.mark.parametrize(
    "row, message",
    [
        (_candidate(symbol="5930"), "symbol"),
        (_candidate(name="  "), "name"),
        (_candidate(selection_date="2026/09/11"), "selection_date"),
        (_candidate(strategy_tag=""), "strategy_tag"),
        (_candidate(intended_holding_period=None), "intended_holding_period"),
        (_candidate(source=""), "source"),
        (_candidate(expires_at="2026-09-12T09:00:00"), "expires_at"),
    ],
)
def test_load_rejects_invalid_candidate_fields(tmp_path, row, message):
    path = tmp_path / "candidates.json"
    _write_payload(path, [row])

    with pytest.raises(ExternalCandidateError, match=message):
        ExternalCandidateProvider(path).load(as_of=AS_OF)


def test_load_rejects_future_selection_date(tmp_path):
    path = tmp_path / "candidates.json"
    _write_payload(path, [_candidate(selection_date="2026-09-12")])

    with pytest.raises(ExternalCandidateError, match="future"):
        ExternalCandidateProvider(path).load(as_of=AS_OF)


def test_load_rejects_duplicate_symbol_and_strategy(tmp_path):
    path = tmp_path / "candidates.json"
    _write_payload(path, [_candidate(), _candidate(name="duplicate")])

    with pytest.raises(ExternalCandidateError, match="duplicate"):
        ExternalCandidateProvider(path).load(as_of=AS_OF)


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "object"),
        ({"schema_version": 2, "candidates": []}, "schema_version"),
        ({"schema_version": 1, "candidates": {}}, "candidates"),
        ({"schema_version": 1, "candidates": ["005930"]}, "candidate"),
    ],
)
def test_load_rejects_invalid_document_shape(tmp_path, payload, message):
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ExternalCandidateError, match=message):
        ExternalCandidateProvider(path).load(as_of=AS_OF)


def test_load_reports_missing_and_malformed_files(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(ExternalCandidateError, match="not found"):
        ExternalCandidateProvider(missing).load(as_of=AS_OF)

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ExternalCandidateError, match="invalid JSON"):
        ExternalCandidateProvider(malformed).load(as_of=AS_OF)
