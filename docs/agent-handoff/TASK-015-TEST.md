# TASK-015 TEST

## Environment

- Windows
- Python 3.10 32-bit
- pytest 7.4.4

## Focused result

```text
python -m pytest -q tests/test_task015_paper_order_block.py
.........                                                                [100%]
9 passed in 0.05s
```

Python 3.8 compatibility check: `9 skipped in 0.03s`, exit code 0. The broker source requires Python 3.10 syntax, so the safety cases run on the project's CI runtime and skip cleanly on the older local interpreter.

Covered cases:

- `PAPER_TRADING=true`, `ALLOW_LIVE_ORDERS=true`
- `PAPER_TRADING=true`, `ALLOW_LIVE_ORDERS=false`
- `PAPER_TRADING=false`, `ALLOW_LIVE_ORDERS=false`
- BUY and SELL order submission
- SELL order cancellation

Every case recorded zero `_send_order_with_retry` calls.

## Full regression result

```text
python -m pytest -q
....................................................................     [100%]
68 passed in 133.36s (0:02:13)
```

## Safety observations

- No QAxWidget or Kiwoom COM object was created.
- No broker connection or actual order API was called.
- No live trading process was started.
