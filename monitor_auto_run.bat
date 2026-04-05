@echo off
cd /d %~dp0

echo ==============================
echo MONITOR START
echo ==============================

python monitor_runtime_risk.py --log-dir logs --latest

pause