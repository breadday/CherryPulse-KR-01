@echo off
cd /d %~dp0

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo =====================================
echo SAVE CONDITION SNAPSHOT START
echo =====================================
echo Python: %PYTHON_EXE%
echo.

"%PYTHON_EXE%" save_condition_snapshot.py

pause
