"""The unattended morning runner must gate time and stop on step failures."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, cast

from tools import r045_morning_run

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

DEMO_DAY = "20261022"


def fake_now(fixed: datetime) -> type[datetime]:
    """Pin datetime.now so fixture paths match the manifest evidence dir."""

    class PinnedDatetime(datetime):
        @classmethod
        def now(cls, _tz: object = None) -> PinnedDatetime:
            return cls(fixed.year, fixed.month, fixed.day, fixed.hour, fixed.minute)

    return PinnedDatetime


def test_market_gate_classifies_market_hours_kst() -> None:
    kst = r045_morning_run.KST
    before = datetime(2026, 10, 20, 8, 59, tzinfo=kst)
    opening = datetime(2026, 10, 20, 9, 0, tzinfo=kst)
    inside = datetime(2026, 10, 21, 12, 0, tzinfo=kst)
    closing_edge = datetime(2026, 10, 27, 15, 20, tzinfo=kst)
    after_close = datetime(2026, 10, 27, 15, 21, tzinfo=kst)
    weekend = datetime(2026, 10, 24, 10, 0, tzinfo=kst)
    naive = datetime(2026, 10, 21, 10, 0)  # noqa: DTZ001 -- An offset-free clock.
    assert r045_morning_run.market_gate(before) == "BEFORE_OPEN"
    assert r045_morning_run.market_gate(opening) == "MARKET_OPEN"
    assert r045_morning_run.market_gate(inside) == "MARKET_OPEN"
    assert r045_morning_run.market_gate(closing_edge) == "MARKET_OPEN"
    assert r045_morning_run.market_gate(after_close) == "AFTER_CLOSE"
    assert r045_morning_run.market_gate(weekend) == "WEEKEND"
    assert r045_morning_run.market_gate(naive) == "CLOCK_UNCERTAIN"


def test_main_refuses_outside_market_window_without_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(_command: list[str]) -> tuple[int, str, str]:
        raise AssertionError

    monkeypatch.setattr(r045_morning_run, "run_command", forbidden)
    monkeypatch.setattr(r045_morning_run, "market_gate", lambda _now: "BEFORE_OPEN")
    assert r045_morning_run.main(["--settle-seconds", "0"]) == 0
    output = capsys.readouterr().out
    assert "BEFORE_OPEN" in output
    assert '"orders_enabled": false' in output


def write_quote(path: Path, price: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps({"005930": {"price": price, "clock": "093501"}}),
        encoding="utf-8",
    )


class Recorder:
    """Play canned exits, write the quote file, and remember all commands."""

    def __init__(self, root: Path, failing_steps: set[str], quote_price: int) -> None:
        self.root = root
        self.failing_steps = failing_steps
        self.price = quote_price
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> tuple[int, str, str]:
        self.commands.append(list(command))
        joined = " ".join(command)
        if "probe_kiwoom_ws" in joined:
            write_quote(self.quote_path(), self.price)
        code = 1 if self.step_name(joined) in self.failing_steps else 0
        return code, "", ""

    def quote_path(self) -> Path:
        return self.root / "results" / f"r045-{DEMO_DAY}" / "last-quote-005930.json"

    def step_name(self, joined: str) -> str:
        if "probe_kiwoom_rest" in joined:
            return "READ" if "--include-history" in joined else "PREWARM"
        if "probe_kiwoom_ws" in joined:
            return "QUOTE"
        if "submit_paper_buy" in joined:
            return "SUBMIT" if "--confirm-execute" in joined else "PREVIEW"
        if "verify_paper_linkage" in joined:
            return "LINKAGE"
        return "OTHER"


def make_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> r045_morning_run.MorningRun:
    monkeypatch.setattr(r045_morning_run, "ROOT", tmp_path)
    monkeypatch.setattr(r045_morning_run, "datetime", fake_now(NAIVE_DAY))
    return r045_morning_run.MorningRun(
        symbol="005930",
        max_pages=3,
        ws_seconds=10,
        settle=0,
        price_cap=100000,
    )


NAIVE_DAY = datetime(2026, 10, 22, 10, 0)  # noqa: DTZ001 -- Fixture value only.


def evidence_path(tmp_path: Path) -> Path:
    return tmp_path / "results" / f"r045-{DEMO_DAY}" / "manifest.json"


def test_full_happy_flow_runs_all_seven_steps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = make_runner(monkeypatch, tmp_path)
    records = Recorder(tmp_path, set(), 70000)
    monkeypatch.setattr(r045_morning_run, "run_command", records.run)
    assert runner.run() == 0
    assert runner.status == "DONE"
    names = [cast("object", item)["step"] for item in runner.manifest["steps"]]
    assert names == [
        "PREWARM",
        "READ_BEFORE",
        "QUOTE_WS",
        "ORDER_PREVIEW",
        "ORDER_SUBMIT",
        "READ_HISTORY_AFTER",
        "LINKAGE",
    ]
    submit = " ".join(records.commands[4])
    assert "submit_paper_buy" in submit
    assert "--confirm-execute" in submit
    saved = json.loads(evidence_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["status"] == "DONE"


def test_read_failure_before_order_is_an_abort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = make_runner(monkeypatch, tmp_path)
    records = Recorder(tmp_path, {"READ"}, 70000)
    monkeypatch.setattr(r045_morning_run, "run_command", records.run)
    assert runner.run() == 1
    assert runner.status == "ABORTED"
    joined = [" ".join(cmd) for cmd in records.commands]
    assert all("submit_paper_buy" not in text for text in joined)


def test_price_over_cap_skips_order_and_keeps_post_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = make_runner(monkeypatch, tmp_path)
    records = Recorder(tmp_path, set(), 150000)
    monkeypatch.setattr(r045_morning_run, "run_command", records.run)
    assert runner.run() == 0
    assert runner.status == "PARTIAL_PRICE_OVER_CAP"
    joined = [" ".join(cmd) for cmd in records.commands]
    assert all("submit_paper_buy" not in text for text in joined)
    assert joined[-1].endswith("--execute-read-only")
