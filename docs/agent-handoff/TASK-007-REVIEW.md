CHANGES_REQUESTED

Evidence:

- The required market-close liveness is not satisfied. `main_live.py` still blocks stale-data recovery at `STALE_REALDATA_DISABLE_AFTER_HHMM` (15:20) and `_recover_broker_session` blocks late-session reconnects at `RECONNECT_DISABLE_AFTER_HHMM`, while automatic shutdown is 15:35. The new heartbeat observes/manages pending state, but it does not restore reconnect/stale recovery through that window.
- The implementation report says `main_live.py` and SQLite schema were not modified, but the diff modifies `main_live.py` and adds the `risk_events` schema plus columns in `infra/sqlite_store.py`. This violates the stated scope and the explicit no-`main_live.py`/no-schema constraint.
- The complete `git diff main` does not contain the reported `tests/test_risk_sell_state_machine.py` or `tests/test_risk_restart_reconcile.py` changes (the files are present in the workspace but absent from the diff). Therefore the claimed failure-path evidence is not part of the reviewable change unless those tests are properly included.
- The submitted tests are not the specified restart end-to-end coverage: `test_risk_restart_reconcile.py` only tests `OrderManager`; it does not create a durable SQLite event and a new `TradingEngine`, nor does it exercise pending/account exceptions, disappearance timeout, or zero place/cancel calls across restart. The test report itself acknowledges this missing coverage.
- `sync_pending_orders` registers a restored order before binding it; if binding fails, the order remains in `orders` despite the manual fail-closed result. This leaves local state inconsistent with the claimed atomic identity contract and is not covered by a test asserting no state mutation on binding failure.

The normal stop path is moved ahead of news/daily/strategy checks, and the reviewed code contains useful identity and cumulative-fill guards, but the liveness, scope, and missing/undelivered failure-path coverage above must be corrected before approval.
