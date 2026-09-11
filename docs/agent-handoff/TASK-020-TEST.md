# TASK-020 TEST

## Focused runner E2E

```text
python -m pytest -q tests/test_task_runner_e2e.py::test_runner_records_baseline_before_stages_and_delivers_exact_scope
.                                                                        [100%]
1 passed in 20.05s
```

Observed behavior:

- runner completed with `TASK_COMPLETE`
- baseline JSON existed and remained readable
- analyzer, implementer, tester, and reviewer logs existed
- baseline JSON and stage logs were absent from normal Git status
- previous ignored log was absent from baseline paths
- SCOPE-MANIFEST and REVIEW remained visible to Git
- reviewer stub read the untracked test and wrote PASS

## Full regression

```text
python -m pytest -q
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 128.22s (0:02:08)
```

The full suite ran with Python 3.10 32-bit and pytest 7.4.4.

## Safety observations

- All OpenCode and Git mutations occurred inside pytest temporary directories.
- No project publish, network, broker, account, or order path was used.
