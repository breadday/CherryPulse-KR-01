import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


if sys.version_info >= (3, 10):
    from selectors import ExternalCandidateError
    from universe_manager import UniverseManager
else:
    ExternalCandidateError = ValueError
    UniverseManager = None


requires_python_310 = pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="UniverseManager annotations require Python 3.10+",
)

AS_OF = datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc)


def _manager(tmp_path: Path):
    return UniverseManager(
        snapshot_path=tmp_path / "snapshot.json",
        fallback_condition_name="test-condition",
        strategy_universe_config={
            "bottom_reversal": {"use_snapshot": True, "use_condition": False},
            "leader_pullback": {"use_snapshot": True, "use_condition": False},
            "momentum": {"use_snapshot": False, "use_condition": True},
        },
        external_candidate_path=tmp_path / "external-candidates.json",
    )


def _candidate(symbol, strategy_tag, expires_at="2026-09-12T09:00:00Z"):
    return {
        "symbol": symbol,
        "name": symbol,
        "selection_date": "2026-09-11",
        "strategy_tag": strategy_tag,
        "intended_holding_period": "3-10d",
        "source": "external-model",
        "expires_at": expires_at,
    }


def _write_candidates(manager, rows):
    manager.external_candidate_path.write_text(
        json.dumps({"schema_version": 1, "candidates": rows}),
        encoding="utf-8",
    )


@requires_python_310
def test_external_candidates_are_isolated_and_merged_by_strategy(tmp_path):
    manager = _manager(tmp_path)
    manager.replace_snapshot_rows(
        [{"symbol": "SNAP", "strategies": ["bottom_reversal"]}]
    )
    manager.add_condition("COND")
    _write_candidates(
        manager,
        [
            _candidate("005930", "bottom_reversal"),
            _candidate("005930", "momentum"),
            _candidate("000660", "leader_pullback"),
        ],
    )

    loaded = manager.load_external_candidates(as_of=AS_OF)

    assert [(item.symbol, item.strategy_tag) for item in loaded] == [
        ("005930", "bottom_reversal"),
        ("005930", "momentum"),
        ("000660", "leader_pullback"),
    ]
    assert manager.external_codes() == ["000660", "005930"]
    assert manager.strategy_source_codes("bottom_reversal", "external") == ["005930"]
    assert manager.strategy_source_codes("leader_pullback", "external") == ["000660"]
    assert manager.strategy_source_codes("momentum", "external") == ["005930"]
    assert manager.strategy_codes("bottom_reversal") == ["005930", "SNAP"]
    assert manager.strategy_codes("momentum") == ["005930", "COND"]


@requires_python_310
def test_expired_reload_clears_only_external_source(tmp_path):
    manager = _manager(tmp_path)
    manager.replace_snapshot_rows(
        [{"symbol": "SNAP", "strategies": ["bottom_reversal"]}]
    )
    manager.add_condition("COND")
    _write_candidates(manager, [_candidate("005930", "bottom_reversal")])
    manager.load_external_candidates(as_of=AS_OF)

    _write_candidates(
        manager,
        [_candidate("005930", "bottom_reversal", "2026-09-11T09:00:00Z")],
    )
    loaded = manager.load_external_candidates(as_of=AS_OF)

    assert loaded == []
    assert manager.external_codes() == []
    assert manager.strategy_codes("bottom_reversal") == ["SNAP"]
    assert manager.strategy_codes("momentum") == ["COND"]


@requires_python_310
def test_invalid_reload_clears_external_but_preserves_other_sources(tmp_path):
    manager = _manager(tmp_path)
    manager.replace_snapshot_rows(
        [{"symbol": "SNAP", "strategies": ["bottom_reversal"]}]
    )
    manager.add_condition("COND")
    _write_candidates(manager, [_candidate("005930", "bottom_reversal")])
    manager.load_external_candidates(as_of=AS_OF)
    manager.external_candidate_path.write_text("{", encoding="utf-8")

    with pytest.raises(ExternalCandidateError, match="invalid JSON"):
        manager.load_external_candidates(as_of=AS_OF)

    assert manager.external_codes() == []
    assert manager.strategy_codes("bottom_reversal") == ["SNAP"]
    assert manager.strategy_codes("momentum") == ["COND"]
    assert manager.should_route("HELD", has_position=True) is True
    assert manager.should_route("PENDING", has_open_order=True) is True


@requires_python_310
def test_missing_reload_clears_previous_external_candidates(tmp_path):
    manager = _manager(tmp_path)
    _write_candidates(manager, [_candidate("005930", "bottom_reversal")])
    manager.load_external_candidates(as_of=AS_OF)
    manager.external_candidate_path.unlink()

    with pytest.raises(ExternalCandidateError, match="not found"):
        manager.load_external_candidates(as_of=AS_OF)

    assert manager.external_codes() == []
    assert manager.all_watch_codes() == []


@requires_python_310
def test_unknown_strategy_tag_fails_closed(tmp_path):
    manager = _manager(tmp_path)
    _write_candidates(manager, [_candidate("005930", "bottom_reversal")])
    manager.load_external_candidates(as_of=AS_OF)
    _write_candidates(manager, [_candidate("000660", "unknown_strategy")])

    with pytest.raises(ExternalCandidateError, match="unknown strategy_tag"):
        manager.load_external_candidates(as_of=AS_OF)

    assert manager.external_codes() == []
    assert manager.all_watch_codes() == []
