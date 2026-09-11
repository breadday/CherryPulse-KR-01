import math
from core.risk_guard import RiskGuard, RiskPosition


def test_boundary_triggers_and_invalid_values_do_not():
    guard = RiskGuard()
    assert guard.check_stop(RiskPosition("A", 98, 100, 10, -0.02)).triggered
    assert not guard.check_stop(RiskPosition("A", 98.01, 100, 10, -0.02)).triggered
    for value in (None, 0, -1, "x", math.nan, math.inf):
        assert guard.check_stop(RiskPosition("A", value, 100, 10, -0.02)).event_type == "INVALID_INPUT"


def test_open_order_and_persisted_event_are_idempotent():
    guard = RiskGuard()
    assert not guard.should_submit("A", "A", True)
    assert guard.should_submit("A", "A", False)
    assert not guard.should_submit("A", "A", False, {"state": "SELL_PARTIAL"})
