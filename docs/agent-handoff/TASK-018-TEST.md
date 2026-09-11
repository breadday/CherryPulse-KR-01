# TASK-018 TEST

## Focused result

```text
python -m pytest -q tests/test_task018_loss_protection.py
....                                                                     [100%]
4 passed in 0.07s
```

Covered behavior:

- current-day realized PnL baseline subtraction
- daily-loss boundary BUY rejection
- per-strategy consecutive-loss isolation
- risk-stop submission while the engine protection flag is active
- risk-stop priority before external data and strategy evaluation

## Full regression

```text
python -m pytest -q
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 139.65s (0:02:19)
```

The full suite ran with Python 3.10 32-bit and pytest 7.4.4.

## Safety observations

- The focused broker was an in-memory stub.
- No GUI, COM, broker connection, network, account, or actual order API was used.
