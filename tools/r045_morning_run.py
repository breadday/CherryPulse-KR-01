"""Unattended R04/R05 morning demo on the assigned PC with recorded user approval.

Approved by the user on 2026-10-21 (option A): the runner executes the
checklist steps -- warmup, read-only probes, one WebSocket quote capture,
one paper 1-share limit buy preview and submission, then a post-order
history and linkage check -- inside the 09:00~15:20 KST market window
only. It never retries an order, never prints credentials, and leaves
all judgement and doc updates to a later supervised review.
"""

# ruff: noqa: INP001 -- Standalone scheduler tool with python -m invocation.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
DEFAULT_SYMBOL = "005930"
PRICE_CAP = 100000
MARKET_OPEN = (9, 0)
MARKET_CLOSE = (15, 20)
WEEKEND_START = 5  # Monday is 0; Saturday is the first weekend weekday.


def market_gate(now: datetime) -> str:
    """Classify the scheduled moment without inferring any trading day."""
    if now.utcoffset() is None:
        return "CLOCK_UNCERTAIN"
    local = now.astimezone(KST)
    if local.weekday() >= WEEKEND_START:
        return "WEEKEND"
    start = local.replace(
        hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0
    )
    end = local.replace(
        hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0
    )
    if local < start:
        return "BEFORE_OPEN"
    if local > end:
        return "AFTER_CLOSE"
    return "MARKET_OPEN"


def run_command(command: list[str]) -> tuple[int, str, str]:
    """One subprocess with bounded output and no shell or env mutation."""
    result = subprocess.run(  # noqa: S603 -- Fixed offline command list.
        command,
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=300,
    )
    return result.returncode, result.stdout, result.stderr


_PARSER = None


class MorningRun:
    """Sequential checklist runner storing one manifest plus a final marker."""

    def __init__(
        self,
        *,
        symbol: str,
        max_pages: int,
        ws_seconds: int,
        settle: int,
        price_cap: int,
    ) -> None:
        """Pin one demo day, evidence folder, and order ceiling for this run."""
        self.symbol = symbol
        self.max_pages = max_pages
        self.ws_seconds = ws_seconds
        self.settle = settle
        self.price_cap = price_cap
        self.day = datetime.now(KST).strftime("%Y%m%d")
        self.evidence = ROOT / "results" / f"r045-{self.day}"
        self.quote_path = self.evidence / f"last-quote-{symbol}.json"
        self.manifest: dict[str, object] = {
            "schema_version": 1,
            "symbol": symbol,
            "day": self.day,
            "steps": [],
            "status": "NOT_STARTED",
        }
        self.status = "NOT_STARTED"
        self._aborted_reason: str | None = None

    def _python(self, *args: str) -> list[str]:
        return [sys.executable, "-m", *args]

    def _step(self, name: str, command: list[str], *, abort_on_failure: bool) -> bool:
        try:
            code, out, err = run_command(command)
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, out, err = -1, "", type(exc).__name__
        item = {
            "step": name,
            "exit_code": code,
            "stdout_bytes": len(out.encode("utf-8")),
            "stderr_bytes": len(err.encode("utf-8")),
        }
        self.manifest["steps"].append(item)
        self._flush()
        if code != 0 and abort_on_failure:
            self.status = "ABORTED"
            self._aborted_reason = f"{name}_FAILED"
            self._flush()
        return code == 0

    def _flush(self) -> None:
        self.manifest["status"] = self.status
        self.evidence.mkdir(parents=True, exist_ok=True)
        destination = self.evidence / "manifest.json"
        _ = destination.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def read_only(self, name: str, *, abort: bool) -> bool:
        """Run one full read-only account probe with history and record it."""
        command = self._python(
            "tools.probe_kiwoom_rest",
            "--execute-read-only",
            "--max-pages",
            str(self.max_pages),
            "--include-history",
        )
        return self._step(name, command, abort_on_failure=abort)

    def quote_capture(self) -> int | None:
        """Capture one live quote; return the approved price or None to skip."""
        command = self._python(
            "tools.probe_kiwoom_ws",
            self.symbol,
            "--seconds",
            str(self.ws_seconds),
            "--execute-read-only",
            "--quote-out",
            str(self.quote_path),
        )
        if not self._step("QUOTE_WS", command, abort_on_failure=True):
            return None
        try:
            book = json.loads(self.quote_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.status = "ABORTED"
            self._aborted_reason = "QUOTE_FILE_UNREADABLE"
            self._flush()
            return None
        quote = book.get(self.symbol)
        if not isinstance(quote, dict):
            self.status = "ABORTED"
            self._aborted_reason = "QUOTE_MISSING"
            self._flush()
            return None
        price = quote.get("price")
        if not isinstance(price, int) or price <= 0:
            self.status = "ABORTED"
            self._aborted_reason = "QUOTE_PRICE_INVALID"
            self._flush()
            return None
        if price > self.price_cap:
            self.status = "PARTIAL_PRICE_OVER_CAP"
            self._aborted_reason = "PRICE_OVER_CAP"
            return None
        return price

    def order_pair(self, price: int) -> None:
        """Preview then submit once; a rejection or UNKNOWN is never retried."""
        self._step(
            "ORDER_PREVIEW",
            self._python(
                "tools.submit_paper_buy",
                "--symbol",
                self.symbol,
                "--price",
                str(price),
            ),
            abort_on_failure=True,
        )
        self._step(
            "ORDER_SUBMIT",
            self._python(
                "tools.submit_paper_buy",
                "--symbol",
                self.symbol,
                "--price",
                str(price),
                "--confirm-execute",
            ),
            abort_on_failure=False,
        )

    def post_checks(self) -> None:
        """Record the post-order history probe and linkage check as evidence."""
        _ = self.read_only("READ_HISTORY_AFTER", abort=False)
        self._step(
            "LINKAGE",
            self._python("tools.verify_paper_linkage", "--execute-read-only"),
            abort_on_failure=False,
        )

    def run(self) -> int:
        """Run the fixed order of steps and persist one completed marker."""
        if not self._step(
            "PREWARM", self._python("tools.probe_kiwoom_rest"), abort_on_failure=True
        ):
            return 1
        if not self.read_only("READ_BEFORE", abort=True):
            return 1
        price = self.quote_capture()
        if self.status == "ABORTED":
            return 1
        if price is not None:
            self.order_pair(price)
            time.sleep(self.settle)
        self.post_checks()
        if self.status == "ABORTED":
            return 1
        if self.status == "NOT_STARTED":
            self.status = "DONE"
        self._flush()
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Accept three bounded tuning knobs; defaults match the checklist."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--ws-seconds", type=int, default=30)
    parser.add_argument("--settle-seconds", type=int, default=30)
    parser.add_argument(
        "--price-cap",
        type=int,
        default=PRICE_CAP,
        help="upper price bound for submit (demo ceiling is 100000)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Refuse to start outside the live market window; otherwise play the steps."""
    argument = parse_args(argv)
    gate = market_gate(datetime.now(timezone.utc))
    if gate != "MARKET_OPEN":
        _ = sys.stdout.write(
            json.dumps({"mode": "PAPER", "orders_enabled": False, "reason": gate})
            + "\n"
        )
        return 0
    runner = MorningRun(
        symbol=argument.symbol,
        max_pages=argument.max_pages,
        ws_seconds=argument.ws_seconds,
        settle=argument.settle_seconds,
        price_cap=argument.price_cap,
    )
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
