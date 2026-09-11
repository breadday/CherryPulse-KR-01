# TASK-003 Review

CHANGES_REQUESTED

Evidence:

- `python -m pytest -q` passes (`6 passed in 0.66s`), and the reported syntax and `git diff --check` checks pass. This is insufficient for the specification’s acceptance set: `tests/test_risk_restart_reconcile.py` and `tests/test_risk_late_session.py` are absent, and only two state-machine cases exist.
- Positive path: `engine.py:on_real_tick` checks a valid positive price with `_check_risk_guard` before news, daily-cache, strategy, and ordinary sell processing. The old stop-loss branch was removed from the ordinary sell path, and an open `RISK_STOP` order is dispatched away from `_retry_sell_after_cancel`.
- Failure in the required safety boundary: `RISK_CANCEL_CONFIRM_TIMEOUT_SEC` and `RISK_RECONCILE_INTERVAL_SEC` are loaded but never consumed. `_check_stale_risk_order` records `CANCEL_REQUESTED`, while confirmation/timeout handling is only indirectly attempted by `sync_pending_orders`; no bounded confirmation-timeout transition to `MANUAL_INTERVENTION_REQUIRED` is implemented.
- Late-session behavior is not implemented in `main_live.py`. `on_heartbeat` returns outside `market_session`, while reconnect is blocked after the configured late-session cutoff and stale recovery is disabled after its cutoff. `shutdown` logs positions, stops the engine, and calls `os._exit(0)` without final risk-event/cancel-pending/broker reconciliation or required risk-state logging. Thus reconnect/stale monitoring is not proven alive through the market-close window.
- Restart reconciliation is incomplete: `_restore_risk_events` can mark an event manual when a broker id is not pending, but it does not establish the specified broker/local matching matrix for ambiguous or missing identifiers, and there is no dedicated `Order` risk metadata or `OrderManager` risk lookup; metadata is attached dynamically in `engine.py`.
- Normal partial-fill, duplicate-fill, retry-limit, cancel-failure/confirmation-timeout, restart, and late-session failure paths are not covered by the executed tests. Consequently the review cannot confirm that stop-loss remains unblocked by grace/trend-hold/news/daily-cache/stale shortcuts under all required conditions.
- Scope evidence: the TASK-003 code diff does not modify broker transport or execute live trading/secrets. The complete diff against `main` also contains pre-existing automation/TASK-001/TASK-002 files; those are unrelated to this task and should remain separately attributable.
