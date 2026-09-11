import sys
from pathlib import Path

import pytest


if sys.version_info >= (3, 10):
    from universe_manager import UniverseManager
else:
    UniverseManager = None


requires_python_310 = pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="UniverseManager annotations require Python 3.10+",
)


def _manager(tmp_path: Path):
    return UniverseManager(
        snapshot_path=tmp_path / "snapshot.json",
        fallback_condition_name="test-condition",
        strategy_universe_config={
            "bottom_reversal": {"use_snapshot": True, "use_condition": False},
            "leader_pullback": {"use_snapshot": True, "use_condition": False},
            "close_buy": {"use_snapshot": True, "use_condition": False},
            "momentum": {"use_snapshot": False, "use_condition": True},
            "vcp_box": {"use_snapshot": False, "use_condition": False},
        },
    )


@requires_python_310
def test_tagged_snapshot_rows_remain_isolated_by_strategy(tmp_path):
    manager = _manager(tmp_path)

    manager.replace_snapshot_rows(
        [
            {"symbol": "BOTTOM", "strategies": ["bottom_reversal"]},
            {"symbol": "LEADER", "strategies": ["leader_pullback"]},
            {"symbol": "CLOSE", "strategies": ["close_buy"]},
            {"symbol": "SHARED", "strategies": ["bottom_reversal", "leader_pullback"]},
        ]
    )

    assert manager.strategy_codes("bottom_reversal") == ["BOTTOM", "SHARED"]
    assert manager.strategy_codes("leader_pullback") == ["LEADER", "SHARED"]
    assert manager.strategy_codes("close_buy") == ["CLOSE"]
    assert manager.strategy_codes("momentum") == []
    assert manager.strategy_codes("vcp_box") == []
    assert manager.strategy_counts() == {
        "bottom_reversal": 2,
        "close_buy": 1,
        "leader_pullback": 2,
        "momentum": 0,
        "vcp_box": 0,
    }


@requires_python_310
def test_condition_removal_does_not_remove_snapshot_membership(tmp_path):
    manager = _manager(tmp_path)
    manager.replace_snapshot_rows(
        [{"symbol": "SHARED", "strategies": ["bottom_reversal"]}]
    )

    manager.add_condition("SHARED")
    manager.add_condition("MOMENTUM")

    assert manager.strategy_codes("bottom_reversal") == ["SHARED"]
    assert manager.strategy_codes("momentum") == ["MOMENTUM", "SHARED"]
    manager.remove_condition("SHARED")
    assert manager.strategy_codes("bottom_reversal") == ["SHARED"]
    assert manager.strategy_codes("momentum") == ["MOMENTUM"]
    assert manager.has_snapshot("SHARED") is True
    assert manager.has_condition("SHARED") is False


@requires_python_310
def test_replacing_snapshot_clears_only_stale_snapshot_memberships(tmp_path):
    manager = _manager(tmp_path)
    manager.replace_snapshot_rows(
        [
            {"symbol": "OLD", "strategies": ["bottom_reversal"]},
            {"symbol": "KEEP", "strategies": ["leader_pullback"]},
        ]
    )
    manager.add_condition("MOMENTUM")

    manager.replace_snapshot_rows(
        [{"symbol": "NEW", "strategies": ["close_buy"]}]
    )

    assert manager.snapshot_codes() == ["NEW"]
    assert manager.strategy_codes("bottom_reversal") == []
    assert manager.strategy_codes("leader_pullback") == []
    assert manager.strategy_codes("close_buy") == ["NEW"]
    assert manager.strategy_codes("momentum") == ["MOMENTUM"]


@requires_python_310
def test_selector_mapping_and_routing_use_exact_strategy_universe(tmp_path):
    manager = _manager(tmp_path)
    manager.replace_snapshot_rows(
        [{"symbol": "BOTTOM", "strategies": ["bottom_reversal"]}]
    )

    assert manager.matches_strategy_universe("bottom_reversal_universe", "BOTTOM") is True
    assert manager.matches_strategy_universe("leader_universe", "BOTTOM") is False
    assert manager.matches_strategy_universe("unknown_universe", "BOTTOM") is False
    assert manager.should_route("BOTTOM") is True
    assert manager.should_route("HELD", has_position=True) is True
    assert manager.should_route("PENDING", has_open_order=True) is True
    assert manager.should_route("UNRELATED") is False
