# TASK-023 TEST

## Focused result

```text
python -m pytest -q tests/test_task023_external_candidate_provider.py
.................                                                        [100%]
17 passed in 0.55s
```

Covered behavior:

- required schema and candidate fields
- normalized immutable candidate values
- timezone offset and UTC `Z` expiration timestamps
- exact expiration boundary exclusion
- Korean market date at the UTC date boundary
- invalid symbol, date, field, document shape, duplicate identity and file errors

## Full regression

```text
python -m pytest -q
........................................................................ [ 70%]
..............................                                           [100%]
102 passed in 144.91s (0:02:24)
```

The full suite ran with Python 3.10 32-bit and pytest 7.4.4.

## Static validation

- Python `compile()` validation passed for the provider, package export and focused test.
- basedpyright was unavailable because the existing environment records a prior declined installation; no LSP result is claimed.
- scoped whitespace and control-character checks passed.

## Safety observations

- Tests used only temporary local JSON files and a fixed clock.
- No live process, broker, network, database, account or order path was executed.
