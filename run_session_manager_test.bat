@echo off
cd /d %~dp0
echo ==============================
echo TEST RUN (Immediate)
echo ==============================
python auto_session_manager.py --trade-script main_live.py --enable-monitor --log-dir logs --start-time 00:00 --stop-time 23:59
pause
