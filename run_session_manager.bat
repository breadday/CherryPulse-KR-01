@echo off
cd /d %~dp0
echo ==============================
echo Auto Session Manager START
echo ==============================
python auto_session_manager.py --trade-script main_live.py --enable-monitor --log-dir logs
pause
