@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo ==========================================
echo BUILD DAILY STRATEGY SNAPSHOT START
echo ==========================================
echo Python: %PYTHON_EXE%
echo Input : data\daily
echo Output: condition_snapshot.json
echo.
"%PYTHON_EXE%" "%~dp0build_daily_strategy_snapshot.py" --input "%~dp0data\daily" --output "%~dp0condition_snapshot.json"

if errorlevel 1 (
  echo.
  echo ERROR OCCURRED
  pause
  exit /b %errorlevel%
)

echo.
echo DONE
pause
endlocal
