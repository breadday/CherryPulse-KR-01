@echo off
echo ===============================================
echo  CherryPulse FID morning capture (09:05, 120s)
echo ===============================================
cd /d E:\hermes-local\workspace\CherryPulse-KR-01
if errorlevel 1 (echo Directory not found. & pause & exit /b 1)
if not exist "%LOCALAPPDATA%\Programs\Python\Python310-32\python.exe" (echo Python 3.10 32-bit not found. & pause & exit /b 1)
echo.
echo Log in on the Kiwoom OpenAPI login window.
echo Select mock trading if you verify with mock.
echo Keep this window open. Collection starts at 09:05 for 120 seconds.
echo No orders, no TR queries, no account changes.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%LOCALAPPDATA%\Programs\Python\Python310-32\python.exe' tools\inspect_kiwoom_realtime.py 005930 --start-at 09:05 --seconds 120 2>&1 | Tee-Object -FilePath (Join-Path ([Environment]::GetFolderPath('Desktop')) ('CherryPulse-quote-' + (Get-Date -Format yyyyMMdd) + '.txt'))"
echo.
echo Done. Check CherryPulse-quote-DATE.txt on the Desktop.
echo Remove account and personal info before sharing.
pause
