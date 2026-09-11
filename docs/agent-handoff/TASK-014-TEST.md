# TASK-014 TEST

## Environment

- Windows
- PowerShell Core 7.6.5
- Python 3.10 32-bit
- pytest 7.4.4

## Results

### PowerShell parser

Command equivalent to the CI step parsed every `scripts/*.ps1` file.

Result: `PowerShell syntax ok`

### Python compile

```text
python -m compileall -q core broker infra engine.py main_live.py tests
```

Result: exit code 0.

### Full test suite

```text
python -m pytest -q
...........................................................              [100%]
59 passed in 137.99s (0:02:17)
```

The suite ran with Python 3.10 32-bit. The local pytest package path was supplied without installing or importing production GUI/broker dependencies.

## Safety observations

- No Kiwoom COM session was created.
- No live trading process or order path was executed.
- No `.env` value was read or changed by the verification commands.
