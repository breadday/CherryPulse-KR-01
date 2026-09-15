@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo ==========================================
echo PREPARE DAILY SNAPSHOT START
echo ==========================================
echo Python: %PYTHON_EXE%
echo Step 1: download daily candles
echo Step 2: build condition_snapshot.json
echo Step 3: validate condition_snapshot.json
echo.

"%PYTHON_EXE%" "%~dp0download_daily_candles.py" --output-dir "%~dp0data\daily" --count 300
if errorlevel 1 (
  echo.
  echo ERROR: daily candle download failed.
  pause
  exit /b %errorlevel%
)

echo.
echo Daily candle download done.
echo.
echo Building daily strategy snapshot...
"%PYTHON_EXE%" "%~dp0build_daily_strategy_snapshot.py" --input "%~dp0data\daily" --output "%~dp0condition_snapshot.json"
if errorlevel 1 (
  echo.
  echo ERROR: daily snapshot build failed.
  pause
  exit /b %errorlevel%
)

echo.
echo Snapshot build done.
echo.
echo Validating daily strategy snapshot...
"%PYTHON_EXE%" "%~dp0validate_daily_snapshot.py" --snapshot "%~dp0condition_snapshot.json"
if errorlevel 1 (
  echo.
  echo ERROR: daily snapshot validation failed.
  pause
  exit /b %errorlevel%
)

echo.
echo PREPARE DAILY SNAPSHOT DONE
pause
endlocal
