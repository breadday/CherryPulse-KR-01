@echo off
cd /d %~dp0

echo ==============================
echo 07:00 STOCK SELECTOR START
echo ==============================

python select_stocks_7am.py --input selection_candidates.json --output selected_stocks.json --top-n 3

pause
