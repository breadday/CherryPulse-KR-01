# TASK-017 TEST

## Focused result

```text
python -m pytest -q tests/test_task017_universe_isolation.py
....                                                                     [100%]
4 passed in 0.08s
```

Covered behavior:

- tagged snapshot strategy isolation
- shared snapshot membership
- condition source isolation and removal
- snapshot replacement without condition loss
- exact selector universe mapping
- routing for active, held, pending, and unrelated symbols

Python 3.8 compatibility check: `4 skipped in 0.04s`, exit code 0. The production module uses Python 3.10 annotation syntax, so these tests run on the configured CI runtime.

## Full regression

```text
python -m pytest -q
........................................................................ [ 93%]
.....                                                                    [100%]
77 passed in 123.39s (0:02:03)
```

The full suite ran with Python 3.10 32-bit and pytest 7.4.4.

## Safety observations

- No production snapshot or market data was accessed.
- No GUI, broker, network, account, or order path was executed.
