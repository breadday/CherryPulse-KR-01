@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo ==========================================
echo DAILY PREPARE AND MAIN LIVE START
echo ==========================================
echo Python: %PYTHON_EXE%
echo Step 1: download daily candles
echo Step 2: build condition_snapshot.json
echo Step 3: validate condition_snapshot.json
echo Step 4: run main_live.py
echo.

"%PYTHON_EXE%" "%~dp0download_daily_candles.py" --output-dir "%~dp0data\daily" --count 300
if errorlevel 1 (
  echo.
  echo ERROR: daily candle download failed. main_live.py will not start.
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
  echo ERROR: daily snapshot build failed. main_live.py will not start.
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
  echo ERROR: daily snapshot validation failed. main_live.py will not start.
  pause
  exit /b %errorlevel%
)

echo.
echo Snapshot validation done.
echo.
echo Starting main_live.py...
"%PYTHON_EXE%" "%~dp0main_live.py"
set "APP_EXIT=%errorlevel%"

echo.
echo main_live.py exited with code %APP_EXIT%.
pause
exit /b %APP_EXIT%
