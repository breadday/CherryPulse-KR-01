@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo MAIN LIVE WRAPPER
echo ==========================================
echo This wrapper prepares daily data first.
echo It will run:
echo 1. download_daily_candles.py
echo 2. build_daily_strategy_snapshot.py
echo 3. validate_daily_snapshot.py
echo 4. main_live.py
echo.

"%~dp0run_daily_prepare_and_main_live.bat"
exit /b %errorlevel%
