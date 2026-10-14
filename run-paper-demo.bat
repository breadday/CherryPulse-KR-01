@echo off
REM CherryPulse paper 1-share limit-buy demo + linkage check (mock only).
REM Usage:
REM   run-paper-demo.bat [price] [symbol]   - submit once, then linkage check
REM   run-paper-demo.bat check [symbol]     - linkage check only, no submit
REM Defaults: price 56600, symbol 403870.
REM Keys come from the process environment only; this file never holds them.
REM Scheduled runs place one order per day at most (dated sentinel).

cd /d E:\hermes-local\workspace\CherryPulse-KR-01
if errorlevel 1 (echo Directory not found. & pause & exit /b 1)
py -3.10-32 --version >nul 2>&1
if errorlevel 1 (echo Python 3.10 32-bit launcher not found. & pause & exit /b 1)
if "%CHERRYPULSE_PAPER_APP_KEY%"=="" goto :nokeys
if "%CHERRYPULSE_PAPER_APP_SECRET%"=="" goto :nokeys

set MODE=demo
set PRICE=56600
set SYMBOL=403870
if /i "%1"=="check" (
  set MODE=check
  if not "%2"=="" set SYMBOL=%2
) else (
  if not "%1"=="" set PRICE=%1
  if not "%2"=="" set SYMBOL=%2
)

echo ===============================================
echo  CherryPulse paper demo - %MODE% %SYMBOL%
echo ===============================================
echo Keys: present (values never shown).
echo.

if "%MODE%"=="check" goto :linkage
echo [1/2] Preview (no keys, no network)...
py -3.10-32 -m tools.submit_paper_buy --symbol %SYMBOL% --price %PRICE%
if errorlevel 1 goto :failed
echo.
echo [2/2] Submit (mock, one per day at most)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& py -3.10-32 -m tools.submit_paper_buy --symbol %SYMBOL% --price %PRICE% --confirm-execute 2>&1 | Tee-Object -FilePath (Join-Path ([Environment]::GetFolderPath('Desktop')) ('CherryPulse-paper-demo-' + (Get-Date -Format yyyyMMdd) + '.txt')); exit $LASTEXITCODE"
if errorlevel 1 goto :linkage_note
goto :linkage

:linkage_note
echo.
echo NOTE: submit did not ack (see Desktop log). Continuing to linkage check.

:linkage
echo.
echo [linkage] Reading history + unfilled (read-only)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& py -3.10-32 -m tools.verify_paper_linkage --execute-read-only --symbol %SYMBOL% 2>&1 | Tee-Object -FilePath (Join-Path ([Environment]::GetFolderPath('Desktop')) ('CherryPulse-paper-demo-' + (Get-Date -Format yyyyMMdd) + '.txt')) -Append; exit $LASTEXITCODE"
if errorlevel 1 goto :failed
echo.
echo Done. Log: Desktop\CherryPulse-paper-demo-DATE.txt (no keys or order numbers inside).
if /i "%3"=="nopause" exit /b 0
pause
exit /b 0

:nokeys
echo.
echo Paper keys are not set in this window. Set them first (values stay in memory only):
echo   $env:CHERRYPULSE_PAPER_APP_KEY = "..."
echo   $env:CHERRYPULSE_PAPER_APP_SECRET = "..."
echo For scheduled runs, store them once with setx (see docs), then re-run.
pause
exit /b 1

:failed
echo.
echo FAILED - see the Desktop log for broker_code / broker_message.
echo Rejection leaves no sentinel, so fixing the cause and re-running is allowed.
echo A second submit on the same day is blocked after an ack or UNKNOWN outcome.
if /i "%3"=="nopause" exit /b 1
pause
exit /b 1
