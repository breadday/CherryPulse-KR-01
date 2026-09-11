# TASK-021 TEST

## Focused result

```text
py -3.8-32 -B -m pytest -q tests/test_task021_broker_timeout.py
.....                                                                    [100%]
5 passed in 0.07s
```

Covered behavior:

- running loop timeout and single quit
- minimum 1000ms timeout and request-label warning
- normal completion without false timeout
- stale callback after loop replacement
- missing loop without timer allocation
- timer stop and deferred-delete cleanup
- login event timeout fails closed without continuing to account/TR requests

The focused timeout suite passes on the project's Python 3.8 32-bit runtime.

## Full regression

```text
py -3.8-32 -B -m pytest -q
111 passed, 18 skipped in 167.90s (0:02:47)
```

The full suite ran with Python 3.8 32-bit and pytest 7.4.4.

## Safety observations

- All timers and loops were in-memory fakes.
- No GUI, COM, broker connection, network, account, TR, condition, or order operation was executed.
