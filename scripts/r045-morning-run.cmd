@echo off
setlocal
cd /d "E:\hermes-local\workspace\CherryPulse-KR-01"
echo === r045 morning run start %date% %time% === >> "results\r045-morning-run.log"
py -3.10 -m tools.r045_morning_run --settle-seconds 30 >> "results\r045-morning-run.log" 2>&1
echo === r045 morning run exit %errorlevel% %date% %time% === >> "results\r045-morning-run.log"
