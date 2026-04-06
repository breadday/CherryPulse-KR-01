
@echo off
cd /d %~dp0

echo [1] 후보 생성
python build_candidates.py

echo [2] 종목 선정
python select_stocks.py

pause
