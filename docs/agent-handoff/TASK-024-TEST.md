# TASK-024 TEST

## Focused result

```text
python -m pytest -q \
  tests/test_task024_external_universe.py \
  tests/test_task017_universe_isolation.py \
  tests/test_task023_external_candidate_provider.py
..........................                                               [100%]
26 passed in 0.26s
```

Covered behavior:

- external strategy-tag isolation and merged strategy universes
- duplicate symbol support across different strategy tags
- expired, missing and malformed reload cleanup
- unknown strategy fail-closed behavior
- snapshot and condition source preservation
- held-position and open-order routing preservation
- TASK-017 and TASK-023 regression contracts

## Full regression

```text
python -m pytest -q
........................................................................ [ 67%]
...................................                                      [100%]
107 passed in 150.19s (0:02:30)
```

The full suite ran with Python 3.10 32-bit and pytest 7.4.4.

## Static validation

- Python syntax and import validation passed for `universe_manager.py` and the focused test.
- basedpyright was unavailable because the environment records a prior declined installation; no LSP result is claimed.
- scoped whitespace and control-character checks passed.

## Safety observations

- No live application, broker, network, database, account or order path was executed.
