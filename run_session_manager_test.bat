@echo off
cd /d %~dp0
echo ==============================
echo TEST RUN (Immediate)
echo ==============================
python auto_session_manager.py --trade-script main_live.py --enable-monitor --log-dir logs --start-time 00:00 --stop-time 23:59
pause


@echo off
cd /d %~dp0
echo ==============================
echo MONITOR ONLY RUN
echo ==============================
python monitor_runtime_risk.py --log-dir logs --latest
pause