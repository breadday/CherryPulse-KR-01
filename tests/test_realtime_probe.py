"""Verify the retired quote probe and retain its pure time parser regression."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import pytest

from tools.inspect_kiwoom_realtime import main, seconds_until_start_at


class RetiredProbePolicyTest(unittest.TestCase):
    """The REST-only runtime retains no active COM observation entrypoint."""

    def test_manual_login_can_wait_for_a_same_day_market_observation(self) -> None:
        morning = datetime(2026, 9, 28, 7, 0, tzinfo=timezone(timedelta(hours=9)))
        target, delay = seconds_until_start_at("09:05", morning)
        assert (target.hour, target.minute, delay) == (9, 5, 7_500)
        for invalid in ("9:05", "25:00", "06:59", "23:59"):
            with pytest.raises(ValueError, match="start time must be"):
                seconds_until_start_at(invalid, morning)

    def test_com_observation_entrypoint_fails_closed(self) -> None:
        assert main() == 2


if __name__ == "__main__":
    unittest.main()
