@echo off
cd /d %~dp0

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo ==============================
echo MAIN LIVE START
echo ==============================
echo Python: %PYTHON_EXE%
echo.

"%PYTHON_EXE%" main_live.py

pause
