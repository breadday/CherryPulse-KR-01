@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo ==========================================
echo VERIFY HARNESS
echo ==========================================
echo Python: %PYTHON_EXE%
echo.

"%PYTHON_EXE%" -B -c "from pathlib import Path; files=['main_live.py','engine.py','broker/kiwoom_broker.py','config_live.py','build_daily_strategy_snapshot.py','universe_manager.py','selectors/snapshot_selector.py']; [compile(Path(p).read_text(encoding='utf-8-sig'), p, 'exec') for p in files]; print('syntax ok')"
if errorlevel 1 goto error

"%PYTHON_EXE%" "%~dp0build_daily_strategy_snapshot.py" --input "%~dp0data\daily" --output "%~dp0condition_snapshot.json"
if errorlevel 1 goto error

"%PYTHON_EXE%" "%~dp0quant_bottom_reversal_backtest.py" --input "%~dp0data\daily"
if errorlevel 1 goto error

echo.
echo VERIFY DONE
pause
exit /b 0

:error
echo.
echo VERIFY FAILED
pause
exit /b 1
