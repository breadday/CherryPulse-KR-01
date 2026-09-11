# PASS

Evidence:

- Daily realized PnL is calculated relative to `daily_realized_pnl_base` and the exact loss-limit boundary blocks a new BUY.
- Consecutive loss protection marks only the affected strategy and leaves the engine and other strategies available.
- With `engine_protected=true`, a valid stop-loss tick still submits exactly one full-quantity `RISK_STOP` SELL.
- The protected stop path runs before strategy generation and external score retrieval.
- Four focused tests and the complete Python 3.10 32-bit suite passed: `81 passed in 139.65s`.
- Production code, configuration, `.env`, broker transport, live enablement, and actual order execution were not changed or run.
