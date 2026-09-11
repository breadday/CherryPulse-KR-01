# PASS

Evidence:

- `.github/workflows/ci.yml` runs on `windows-latest` for push and pull requests with `contents: read` permission.
- The workflow pins Python 3.10 x86 and pytest 7.4.4, matching the project's 32-bit runtime constraint while keeping GUI and broker dependencies out of headless CI.
- The PowerShell parser check passed for every `scripts/*.ps1` file.
- Python compilation passed for core, broker, infra, engine, main entrypoint, and tests.
- The complete suite passed under Python 3.10 32-bit: `59 passed in 137.99s`.
- Trading logic, `.env`, broker transport, live enablement, and order execution were not changed or executed.

Residual verification:

- The workflow steps were reproduced locally. The hosted GitHub Actions run will begin only after these files are committed and pushed.
