@echo off
cd /d %~dp0

echo ==============================
echo 07:00 BUILD + SELECT + MAIN
echo ==============================

python build_candidates_kiwoom_7am.py
if errorlevel 1 goto :err

python select_stocks_7am.py
if errorlevel 1 goto :err

python main_live.py
goto :eof

:err
echo 오류 발생
pause
