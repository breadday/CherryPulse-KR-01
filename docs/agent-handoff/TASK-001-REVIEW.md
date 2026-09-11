# TASK-001 Review

BLOCKED

## Evidence

- The required pytest command did not run: `pytest` is not installed. The engine priority test also cannot be imported under the reported Python 3.8 runtime because the existing `tuple[...]` annotation fails during import.
- Only the pure `RiskGuard` and SQLite tests were executed directly. The required engine priority, risk-order submission, fill/partial-fill, timeout/cancel/retry, manual-intervention, stale/reconnect, and engine restart acceptance paths remain unverified. This does not prove both normal and failure paths.
- The implementation does place `_check_risk_guard` before external scores, daily-cache loading, strategy execution, and ordinary auto-exit processing. The removed legacy stop-loss branch and separate `_submit_risk_sell` do not call `_auto_sell_allowed_now`, grace, or trend-hold. The existing `main_live.py` watch list also retains held positions and open orders, and no broker transport file was modified.
- The risk-specific timeout/cancel/retry contract is not implemented. `_check_stale_sell_order` and `_retry_sell_after_cancel` still operate through the generic order state and generic `_auto_sell_allowed_now` path; risk orders are not marked or separately bounded there. A submitted stop order can therefore be canceled/retried by ordinary logic and subsequently be blocked by the normal sell time gate, contrary to the specification.
- Recovery is only a read/log pass in `_restore_risk_events`: it closes events when the current position is zero and maps an existing local order id, but it does not reconcile broker/open-order state or implement risk-specific finite retry/manual-intervention transitions. No engine-level recovery test was run.
- The late-session behavior is not demonstrated. `main_live.py` retains `RECONNECT_DISABLE_AFTER_HHMM = "14:40"`, `STALE_REALDATA_DISABLE_AFTER_HHMM = "15:20"`, and `AUTO_SHUTDOWN_HHMM = "15:35"`; no test proves that held-position risk monitoring remains safely alive through that window when ticks stop or reconnect is blocked. A received valid tick can reach the guard, but a missing tick cannot produce an automatic stop order, and the required observation/manual-intervention behavior is not persisted or tested.
- No live trading, broker transport, secret, or account changes were found in the task implementation diff. The branch also contains pre-existing automation/docs additions relative to `main`; they are unrelated to the RiskGuard implementation and should not be treated as task evidence.

The implementation and verification need to be completed in the project-compatible Python environment, with the full specified pytest set and explicit tests for late-session routing, risk-specific timeout/cancel/retry, storage failure, rejection, partial fills, and restart reconciliation before approval.
