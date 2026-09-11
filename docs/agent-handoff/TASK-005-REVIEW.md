CHANGES_REQUESTED

Evidence:

- The required test suite is not passing. `python -m pytest -q` reproduces `6 passed, 2 failed`:
  `test_cancel_request_waits_for_broker_disappearance` records zero cancels, and
  `test_pending_risk_order_is_reconciled_without_resubmit` raises `IndexError` because the
  risk event is no longer open. The handoff test report also confirms that the required
  restart and late-session test files are absent.
- There is a blocking implementation defect in `engine.py:_check_stale_risk_order`:
  `broker_id` assignment is indented beneath an unconditional `return` (around lines
  2920-2927). Consequently the cancel path cannot use the confirmed broker ID and then
  references an unbound variable. This directly defeats the required timeout ->
  `CANCEL_REQUESTED` behavior.
- `core/models.py` still has no formal `purpose`, `risk_event_id`, or `broker_order_id`
  fields, and `core/order_manager.py` still uses symbol/recent-order inference for
  broker binding. This does not meet the explicit local-ID/broker-ID and unambiguous
  risk-event binding contract.
- `_submit_risk_sell` only filters the post-submit pending snapshot by symbol, side, and
  presence of `order_no`; it does not enforce the specified risk context/quantity/time
  matching or atomically bind through a risk-specific helper. The implementation also
  does not provide the required durable partial-fill/restart matrix.
- The stop check is correctly placed before news, daily-cache, strategy, and ordinary
  sell gates, so a valid tick is not blocked by those gates. Conversely, stale data does
  not create a new stop, and `on_heartbeat` observes risk before shutdown; these portions
  are directionally correct. They are not sufficient for acceptance because the cancel,
  reconciliation, and retry paths remain unproven and currently fail.
- Reconnect blocking after 14:40 and stale-recovery blocking after 15:20 remain visible,
  while heartbeat risk observation continues. However, shutdown calls are only isolated
  with `try/except`; no bounded timeout/worker wrapper was added around the synchronous
  pending/account calls, contrary to the specification. A broker/API hang can therefore
  prevent the intended final reconciliation and close-window behavior.
- The complete diff against `main` includes unrelated automation/configuration and
  documentation changes (`.opencode/`, `opencode.jsonc`, `scripts/`, and broad docs),
  as well as `core/risk_manager.py`, outside the TASK-005 implementation contract.
  These should be separated or explicitly justified before approval.
- No live broker, COM, secret, or live-trading execution was observed in the supplied
  reports, which is appropriate; however, the missing failure-path tests mean there is
  no evidence for ID ambiguity, query/storage failure, duplicate/partial fills, retry
  limits, or the 14:40/15:20/15:35 boundaries.

Required before approval: fix the risk cancel state-machine defect; add the formal model,
order-manager, durable reconciliation, bounded shutdown, restart, and late-session
coverage required by TASK-005; update incompatible fixtures/tests to use distinct local
and broker IDs; pass the full pytest suite, Python 3.8 compile check, and `git diff --check`.
